"""Session 直驱执行器 — 离线/本地 LLM Provider 模式.

把 skill 文档里教给 Agent 的编排循环（next → prompt → 执行 → parse → summarize）
搬进确定性代码：引擎自己调 OpenAI 兼容 API，编排零 LLM 参与。

设计原则：
- 每次 LLM 调用都是无状态单 prompt，严格受 session.token_budget 约束；
  不存在任何会随流程增长的"编排上下文"。
- 跨 Section 状态全在 ContextStore + checkpoint（磁盘），中断后重跑
  `session run` 自动跳过已完成的 Section 续传。
- 关键节点停下来交给人判断：feed_more（缺输入）、连续失败、质检不过
  都以事件报告并退出，不硬闯。
"""

from __future__ import annotations

import json

from paper_derived.engine.session_engine import (
    build_section_prompt,
    build_summarize_prompt,
    parse_section_result,
    parse_summarize_result,
    session_next,
)
from paper_derived.llm import LLMClient, LLMError
from paper_derived.session_store import checkpoint_session, load_session

# 解析失败后追加到下一次尝试的格式修正指令（小模型 JSON 输出弱，修复循环必备）
_REPAIR_NOTE = (
    "\n\n## 格式修正\n"
    "你上一次的输出无法被解析。这次只输出要求的 JSON 对象本身："
    "不要任何解释、前后缀或 markdown 代码块之外的文字。"
)


def _emit(on_event, event: str, **fields) -> None:
    if on_event:
        on_event({"event": event, **fields})


def _apply_window(session_id: str, window: int, on_event) -> None:
    """按 provider 窗口收缩 session 预算：budget = min(现值, window // 2)。"""
    if window <= 0:
        return
    session, store, doc = load_session(session_id)
    effective = min(session.token_budget, window // 2)
    if effective != session.token_budget:
        _emit(on_event, "budget_adjusted",
              window=window, old_budget=session.token_budget, new_budget=effective)
        session.token_budget = effective
        checkpoint_session(session, store, doc)


def _reset_stale_generating(session_id: str, on_event) -> list[str]:
    """直驱模式没有并发工作者，generating 状态只可能是上次中断的残留 → 重置为 ready。"""
    session, store, doc = load_session(session_id)
    stale = [sid for sid, sp in session.section_progress.items() if sp.status == "generating"]
    for sid in stale:
        session.section_progress[sid].status = "ready"
    if stale:
        checkpoint_session(session, store, doc)
        _emit(on_event, "stale_reset", sections=stale)
    return stale


def _mark_failed(session_id: str, section_id: str) -> None:
    session, store, doc = load_session(session_id)
    if section_id in session.section_progress:
        session.section_progress[section_id].status = "failed"
        checkpoint_session(session, store, doc)


def _generate_section(
    session_id: str,
    section_id: str,
    client: LLMClient,
    max_attempts: int,
    do_summarize: bool,
    on_event,
) -> bool:
    """生成单个 Section（含解析修复重试 + 摘要）。返回是否成功。"""
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        system, user = build_section_prompt(session_id, section_id)
        if attempt > 1:
            user += _REPAIR_NOTE
        try:
            response = client.chat(system, user)
        except LLMError as e:
            last_error = str(e)
            _emit(on_event, "llm_error", section=section_id, attempt=attempt, error=last_error)
            continue
        try:
            report = parse_section_result(response, session_id, section_id)
        except Exception as e:
            last_error = f"解析失败: {e}"
            _emit(on_event, "parse_retry", section=section_id, attempt=attempt, error=str(e)[:200])
            continue

        _emit(on_event, "section_done", section=section_id,
              section_status=report.get("section_status", ""),
              progress=report.get("progress", ""), attempts=attempt)

        if do_summarize:
            _summarize_section(session_id, section_id, client, on_event)
        return True

    _mark_failed(session_id, section_id)
    _emit(on_event, "section_failed", section=section_id,
          attempts=max_attempts, error=last_error[:300])
    return False


def _summarize_section(session_id: str, section_id: str, client: LLMClient, on_event) -> None:
    """生成并存储 Section 摘要。失败不阻断流程（下游 prompt 会退化为装更多原文）。"""
    try:
        system, user = build_summarize_prompt(session_id, section_id)
        response = client.chat(system, user, max_tokens=1024)
        parse_summarize_result(response, session_id, section_id)
        _emit(on_event, "summarized", section=section_id)
    except Exception as e:
        _emit(on_event, "summarize_skipped", section=section_id, error=str(e)[:200])


def run_session(
    session_id: str,
    client: LLMClient,
    window: int = 0,
    max_sections: int = 0,
    do_summarize: bool = True,
    max_attempts: int = 3,
    on_event=None,
) -> dict:
    """驱动 session 的生成循环直到 assemble 就绪 / 需要输入 / 无法推进。

    Returns:
        总结 dict: {"status": "ready_to_assemble" | "needs_input" | "stuck"
                    | "section_limit_reached", "progress": "12/38", "failed": [...]}
    """
    _apply_window(session_id, window, on_event)
    _reset_stale_generating(session_id, on_event)

    processed = 0
    failed: list[str] = []
    waited_once = False

    session, _, _ = load_session(session_id)
    max_iterations = session.total_sections * max_attempts + 20

    for _ in range(max_iterations):
        nxt = session_next(session_id)
        action = nxt.get("action", "")

        if action == "assemble":
            return _finish(session_id, "ready_to_assemble", failed, on_event)

        if action == "feed_more":
            _emit(on_event, "needs_input",
                  pending_sections=nxt.get("pending_sections", []),
                  message=nxt.get("message", ""))
            return _finish(session_id, "needs_input", failed, on_event)

        if action == "wait":
            # 直驱模式下 wait 只可能来自残留状态；重置一次，再出现即无法推进
            if waited_once or not _reset_stale_generating(session_id, on_event):
                return _finish(session_id, "stuck", failed, on_event)
            waited_once = True
            continue

        if action == "generate":
            batch = nxt.get("parallel_batch") or [nxt["section_id"]]
            for sid in batch:
                if max_sections and processed >= max_sections:
                    return _finish(session_id, "section_limit_reached", failed, on_event)
                ok = _generate_section(
                    session_id, sid, client, max_attempts, do_summarize, on_event
                )
                processed += 1
                if not ok:
                    failed.append(sid)
            continue

        return _finish(session_id, "stuck", failed, on_event)

    return _finish(session_id, "stuck", failed, on_event)


def _finish(session_id: str, status: str, failed: list[str], on_event) -> dict:
    session, _, _ = load_session(session_id)
    summary = {
        "status": status,
        "session_id": session_id,
        "progress": f"{session.done_sections}/{session.total_sections}",
        "failed": failed,
        "phase": session.phase,
    }
    _emit(on_event, "run_finished", **summary)
    return summary

# ═══════════════════════════════════════════════════════════════
#  小模型友好流水线（~30B 级 Provider 可稳定完成）
# ═══════════════════════════════════════════════════════════════


class PipelineError(RuntimeError):
    """流水线步骤在重试耗尽后仍失败。"""


def _chat_parse(client, system, user, parse_fn, attempts=3, on_event=None, label=""):
    """调用 LLM 并解析；解析失败自动附加格式修正指令重试。"""
    last = ""
    for i in range(1, attempts + 1):
        u = user + (_REPAIR_NOTE if i > 1 else "")
        try:
            resp = client.chat(system, u)
        except LLMError as e:
            last = str(e)
            _emit(on_event, "llm_error", step=label, attempt=i, error=last[:200])
            continue
        try:
            return parse_fn(resp)
        except Exception as e:
            last = f"解析失败: {e}"
            _emit(on_event, "parse_retry", step=label, attempt=i, error=str(e)[:200])
    raise PipelineError(f"{label}: 重试 {attempts} 次后仍失败 — {last[:300]}")


def _chat_text(client, system, user, attempts=2, on_event=None, label="") -> str:
    """调用 LLM 拿纯文本（非 JSON 任务，小模型最稳的输出形态）。"""
    return _chat_parse(
        client, system, user,
        parse_fn=lambda r: (r.strip() or (_ for _ in ()).throw(ValueError("空响应"))),
        attempts=attempts, on_event=on_event, label=label,
    )


# ── 模板注册直驱：结构确定性扫描 + LLM 只写三段小文本 ──────────


_TPL_MODULE_SPECS = [
    ("extraction_prompt",
     "你是文档模板分析师。基于章节清单与样例节选，写一段【抽取指令】：说明为各章节从输入资料中提取内容时，"
     "应从哪类输入查找、匹配什么特征、如何组织输出。按章节分组表述。"
     "纯文本输出，不要 markdown 标题行，不超过 600 字。"),
    ("style_prompt",
     "你是文档模板分析师。基于样例节选，写一段【风格指令】：总结样例的术语使用习惯、叙述语气、"
     "表格/列表的使用习惯、代码块语言偏好。生成文档时将逐条遵循。"
     "纯文本输出，不要 markdown 标题行，不超过 400 字。"),
    ("validation_prompt",
     "你是文档模板分析师。基于章节清单与样例节选，写一份【校验指令】：列出 5-10 条生成文档后可逐项检查的"
     "质量规则，每条末尾标注 (fixable) 或 (input_dependent)。"
     "纯文本编号清单输出，不要 markdown 标题行。"),
]


def register_template_auto(
    sample_text: str,
    name: str,
    description: str,
    client: LLMClient,
    window: int = 0,
    on_event=None,
):
    """小模型友好的模板注册：

    结构骨架由 scan_section_tree 确定性构建（LLM 不生成树、不写大 JSON），
    structure_prompt 从树确定性渲染；LLM 仅执行 3 次小的纯文本调用
    （抽取/风格/校验指令模块）。
    """
    from datetime import datetime, timezone
    from paper_derived.engine.template import (
        scan_section_tree, scan_top_headings, render_structure_prompt,
        _extract_section_ids, _extract_dependencies, _to_kebab_case,
    )
    from paper_derived.models.template import Template
    from paper_derived.storage import save_template, find_template_by_name

    if find_template_by_name(name):
        raise PipelineError(f"模板「{name}」已存在，先 template delete 再注册")

    tree = scan_section_tree(sample_text)
    if not tree:
        raise PipelineError("未能从样例扫描出章节结构（无编号标题也无 markdown 标题），"
                            "请改用 template register 的 Agent 路径")
    section_ids = _extract_section_ids(tree)
    _emit(on_event, "tree_scanned", sections=len(section_ids),
          top_level=[n["title"] for n in tree])

    # 样例节选：按窗口截取（中文 1 字≈1 token；给指令和输出留余量）
    excerpt_chars = max(3000, int(window * 0.5)) if window else 20000
    excerpt = sample_text[:excerpt_chars]
    if len(sample_text) > excerpt_chars:
        excerpt += "\n\n（样例后文已截断）"
    anchor_block = "\n".join(f"- {a['number']} {a['title']}" for a in scan_top_headings(sample_text))
    user_base = f"## 章节清单\n{anchor_block}\n\n## 样例文档节选\n\n{excerpt}"

    modules = {"structure_prompt": render_structure_prompt(tree)}
    for field_name, instruction in _TPL_MODULE_SPECS:
        modules[field_name] = _chat_text(
            client, instruction, user_base,
            attempts=3, on_event=on_event, label=field_name,
        )
        _emit(on_event, "module_generated", module=field_name,
              chars=len(modules[field_name]))

    now = datetime.now(timezone.utc).isoformat()
    tpl_id = _to_kebab_case(name)
    if tpl_id == "template":  # 全非 ASCII 名称（如中文）的兜底：稳定短哈希
        import hashlib
        tpl_id = "tpl-" + hashlib.md5(name.encode("utf-8")).hexdigest()[:8]
    template = Template(
        id=tpl_id,
        name=name,
        description=description,
        extraction_prompt=modules["extraction_prompt"],
        structure_prompt=modules["structure_prompt"],
        style_prompt=modules["style_prompt"],
        validation_prompt=modules["validation_prompt"],
        section_ids=section_ids,
        section_dependencies=_extract_dependencies(tree),
        section_tree=tree,
        created_at=now,
        updated_at=now,
    )
    save_template(template)
    _emit(on_event, "template_registered", template_id=template.id,
          sections=len(section_ids), structure_source="deterministic-scan")
    return template


# ── 生成一条龙：原始资料 → 交付文档 ────────────────────────────


def run_pipeline(
    template_id: str,
    input_files: list[str],
    client: LLMClient,
    window: int = 0,
    workdir: str = ".pd",
    output: str = "",
    output_format: str | None = None,
    max_sections: int = 0,
    do_summarize: bool = True,
    max_attempts: int = 3,
    on_event=None,
) -> dict:
    """原始资料 → 注册输入（分块）→ session init/feed → 逐节生成 → 组装交付。

    过程文件全部落 workdir（默认 .pd/），可断点续传：已注册的资产跳过，
    session id 记在 workdir/pipeline.json，生成进度由 checkpoint 托管。
    """
    import json as _json
    from pathlib import Path
    from paper_derived.engine.input_asset import (
        build_register_input_prompt, build_register_input_chunk_prompt,
        parse_register_input_result, merge_input_assets,
    )
    from paper_derived.engine.session_engine import (
        session_init, build_feed_prompt, parse_feed_result, session_assemble,
    )
    from paper_derived.format_reader import read_file, chunk_text, DEFAULT_CHUNK_SIZE
    from paper_derived.format_writer import write_document

    wd = Path(workdir)
    (wd / "assets").mkdir(parents=True, exist_ok=True)
    chunk_chars = max(2000, int(window * 0.35)) if window else DEFAULT_CHUNK_SIZE

    # 1) 注册输入资产（已存在则跳过 → 断点续传）
    asset_paths: list[Path] = []
    for f in input_files:
        name = Path(f).stem
        asset_path = wd / "assets" / f"input-{name}.json"
        asset_paths.append(asset_path)
        if asset_path.exists():
            _emit(on_event, "asset_skipped", file=f, asset=str(asset_path))
            continue
        raw, _, _ = read_file(f)
        chunks = chunk_text(raw, max_chars=chunk_chars)
        partials = []
        for i, chunk in enumerate(chunks):
            if len(chunks) == 1:
                sys_p, user_p = build_register_input_prompt(raw, name)
            else:
                sys_p, user_p = build_register_input_chunk_prompt(
                    chunk, name, chunk_index=i, total_chunks=len(chunks))
            partial = _chat_parse(
                client, sys_p, user_p,
                parse_fn=lambda r: parse_register_input_result(r, "", name, source=f, slim=True),
                attempts=max_attempts, on_event=on_event,
                label=f"register:{name}#{i + 1}/{len(chunks)}",
            )
            partials.append(partial)
            _emit(on_event, "chunk_registered", file=f, chunk=f"{i + 1}/{len(chunks)}")
        asset = merge_input_assets(partials, "", name, source=f, slim=True) \
            if len(partials) > 1 else partials[0]
        asset_path.write_text(_json.dumps(asset.to_dict(), ensure_ascii=False, indent=2),
                              encoding="utf-8")
        _emit(on_event, "asset_registered", file=f, asset=str(asset_path),
              entities=len(asset.entities))

    # 2) session：复用（续传）或新建
    state_file = wd / "pipeline.json"
    state = _json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
    session_id = state.get(template_id, "")
    fed = False
    if session_id:
        try:
            sess, _, _ = load_session(session_id)
            fed = sess.phase not in ("init",)
            _emit(on_event, "session_resumed", session_id=session_id, phase=sess.phase)
        except Exception:
            session_id = ""
    if not session_id:
        budget = min(60_000, window // 2) if window else 60_000
        sess = session_init(template_id, token_budget=budget,
                            output_path=output, output_format=output_format or "")
        session_id = sess.session_id
        state[template_id] = session_id
        state_file.write_text(_json.dumps(state, ensure_ascii=False), encoding="utf-8")
        _emit(on_event, "session_created", session_id=session_id, budget=budget)

    # 3) feed（仅未喂入过时）
    if not fed:
        sess, _, _ = load_session(session_id)
        asset_dicts = [_json.loads(p.read_text(encoding="utf-8")) for p in asset_paths]
        sys_p, user_p = build_feed_prompt(sess, asset_dicts)
        report = _chat_parse(
            client, sys_p, user_p,
            parse_fn=lambda r: parse_feed_result(r, session_id),
            attempts=max_attempts, on_event=on_event, label="feed",
        )
        _emit(on_event, "fed", entities=report.get("entities_extracted", 0),
              data_gaps=report.get("data_gaps", []))

    # 4) 生成循环
    summary = run_session(
        session_id, client, window=window, max_sections=max_sections,
        do_summarize=do_summarize, max_attempts=max_attempts, on_event=on_event,
    )

    # 5) 组装交付
    if summary["status"] == "ready_to_assemble" and output:
        doc = session_assemble(session_id)
        written = write_document(doc, output, fmt=output_format)
        summary["output"] = str(written)
        _emit(on_event, "delivered", output=str(written))
    return summary
