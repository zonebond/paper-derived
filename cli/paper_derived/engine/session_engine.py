"""Session 引擎 — 所有 session 命令的实现.

每个命令遵循现有模式:
  - 无 --parse 标志 → 输出 prompt JSON (Agent 发给 LLM)
  - 有 --parse 标志 → 解析 LLM 响应, 更新 session 状态

Agent 只看到声明式接口和简洁的状态报告,
不看到 ContextStore 内部的原始数据。
"""

from __future__ import annotations

import json
from pathlib import Path

from paper_derived.engine._paths import PROMPTS_DIR
from paper_derived.engine._tokens import count_tokens
from paper_derived.engine.context_assembler import assemble_section_context
from paper_derived.models.session import GenerationSession, SectionProgress, make_session_id, now_iso
from paper_derived.models.context import (
    ContextStore,
    ContextEntity,
    SectionExtraction,
    SectionSummary,
    AssembledContext,
)
from paper_derived.models.document import DocumentTree, Section
from paper_derived.session_store import (
    checkpoint_session,
    load_session,
    save_session,
    save_document,
    delete_session,
)
from paper_derived.storage import load_template


def _read_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
#  session init
# ═══════════════════════════════════════════════════════════════


def session_init(
    template_id: str,
    token_budget: int = 60_000,
    output_path: str = "",
    output_format: str = "",
) -> GenerationSession:
    """初始化生成 Session.

    创建 session, 构建 DocumentTree 骨架,
    从模板 section_dependencies 初始化 SectionProgress。
    无需 LLM。
    """
    template = load_template(template_id)
    if template is None:
        raise ValueError(f"模板不存在: {template_id}")

    doc = DocumentTree.from_template(template_id)

    # 构建 section_progress
    section_progress = {}
    all_ids = doc.collect_section_ids()
    for sid in all_ids:
        dep_info = template.section_dependencies.get(sid, {})
        dep_type = dep_info.get("type", "self_contained")
        sources = dep_info.get("sources", [])
        section_progress[sid] = SectionProgress(
            section_id=sid,
            status="pending",
            depends_on=sources if dep_type == "input_dependent" else [],
        )

    now = now_iso()
    session = GenerationSession(
        session_id=make_session_id(),
        template_id=template_id,
        created_at=now,
        updated_at=now,
        phase="init",
        section_progress=section_progress,
        token_budget=token_budget,
        output_path=output_path,
        output_format=output_format,
    )

    # 初始化空的 ContextStore
    store = ContextStore()

    checkpoint_session(session, store, doc)
    return session


# ═══════════════════════════════════════════════════════════════
#  session feed
# ═══════════════════════════════════════════════════════════════


def build_feed_prompt(
    session: GenerationSession,
    input_assets: list[dict],
) -> tuple[str, str]:
    """构建 ctx:feed 的 prompt.

    Args:
        session: 当前 session
        input_assets: InputAsset 的 to_dict() 列表

    Returns:
        (system_prompt, user_message)
    """
    template = load_template(session.template_id)
    if template is None:
        raise ValueError(f"模板不存在: {session.template_id}")

    system_prompt = _read_prompt("ctx_feed.md")

    parts = [
        f"## 目标模板: {template.name} (ID: {template.id})",
        f"\n### 模板结构指令\n{template.structure_prompt}",
        f"\n### 模板抽取指令\n{template.extraction_prompt}",
        f"\n## Section 列表\n{json.dumps(template.section_ids, ensure_ascii=False)}",
        f"\n## 输入资产 ({len(input_assets)} 份)",
    ]

    for a in input_assets:
        parts.append(f"\n### 资产: {a.get('name', '')} (ID: {a.get('id', '')})")
        parts.append(f"摘要: {a.get('summary', '')}")

        raw = a.get("raw_content", "")
        if raw and len(raw) <= 20_000:
            parts.append(f"\n原始内容:\n{raw}")
        elif a.get("entities"):
            entities_text = json.dumps(a["entities"], ensure_ascii=False, indent=2)
            parts.append(f"\n实体列表:\n{entities_text}")

    return system_prompt, "\n\n".join(parts)


def parse_feed_result(
    llm_response: str,
    session_id: str,
) -> dict:
    """解析 ctx:feed 的 LLM 响应, 更新 ContextStore。

    Agent 只看到状态报告, 不看到内部数据。

    Returns:
        状态报告 dict: {status, entities_extracted, sections_ready, data_gaps}
    """
    from paper_derived.llm import extract_json

    session, store, doc = load_session(session_id)


    result = extract_json(llm_response)

    # 解析 entities → entity_index
    # _key_remap: LLM 返回的 base_key → 因冲突修正后的 actual_key
    _key_remap: dict[str, str] = {}
    entity_count = 0
    for e_data in result.get("entities", []):
        entity = ContextEntity(
            kind=e_data.get("kind", ""),
            name=e_data.get("name", ""),
            description=e_data.get("description", ""),
            attributes=e_data.get("attributes", {}),
            source_input_id=e_data.get("source_input_id", ""),
            source_location=e_data.get("source_location", ""),
            confidence=e_data.get("confidence", 0.0),
            related_sections=e_data.get("related_sections", []),
            token_count=0,
        )
        entity.token_count = count_tokens(
            entity.description + json.dumps(entity.attributes, ensure_ascii=False)
        )
        # 处理 key 冲突: 同 kind:name 不同 source → 追加 source_input_id
        base_key = entity.key  # kind:name
        key = base_key
        if key in store.entity_index and entity.source_input_id:
            key = f"{key}:{entity.source_input_id}"
        store.entity_index[key] = entity
        entity_count += 1
        # 记录 LLM 使用的 key → 实际存储 key 的映射
        # LLM 返回的 entity_keys 用 kind:name 格式，需要修正为实际存储的 key
        if key != base_key:
            _key_remap[base_key] = key

    # 解析 sections → extraction_map
    ready_count = 0
    data_gaps = []
    for sec_data in result.get("sections", []):
        sid = sec_data.get("section_id", "")
        # 修正 entity_keys: LLM 返回的 base_key → 实际存储 key
        raw_keys = sec_data.get("entity_keys", [])
        resolved_keys = [_key_remap.get(k, k) for k in raw_keys]
        sec_extract = SectionExtraction(
            section_id=sid,
            section_title=sec_data.get("section_title", ""),
            entity_keys=resolved_keys,
            confidence=sec_data.get("confidence", 0.0),
            hint=sec_data.get("hint", ""),
        )
        store.extraction_map[sid] = sec_extract

        # 更新 section_progress: 有实体的 section 标记为 ready
        if sid in session.section_progress:
            if session.section_progress[sid].status == "pending":
                session.section_progress[sid].status = "ready"
                ready_count += 1
        if sec_extract.hint:
            data_gaps.append({"section_id": sid, "hint": sec_extract.hint})

    # 解析 fragments → raw_fragments
    for frag in result.get("fragments", []):
        key = frag.get("entity_key", "")
        text = frag.get("text", "")
        if key and text:
            store.raw_fragments[key] = text

    # 记录输入资产
    input_ids = [e.get("source_input_id", "") for e in result.get("entities", [])]
    for iid in input_ids:
        if iid and iid not in session.input_asset_ids:
            session.input_asset_ids.append(iid)

    session.phase = "feeding"
    checkpoint_session(session, store, doc)

    # 构建 next_hint
    total = session.total_sections
    ready = len(session.ready_sections)
    if data_gaps:
        hint = f"有 {len(data_gaps)} 个数据缺口，建议告知用户。补完后可 session feed 继续填充，或直接 session next -s {session_id} 开始生成。"
    else:
        hint = f"输入已消化（{entity_count} 实体, {ready}/{total} Section 就绪）。下一步: session next -s {session_id}"

    return {
        "status": "ok",
        "entities_extracted": entity_count,
        "sections_ready": ready_count,
        "data_gaps": data_gaps,
        "next_hint": hint,
    }


# ═══════════════════════════════════════════════════════════════
#  session next
# ═══════════════════════════════════════════════════════════════


def session_next(session_id: str) -> dict:
    """查询下一步操作。无需 LLM。

    Returns:
        {"action": "generate", "section_id": "..."} 单 Section
        {"action": "generate", "parallel_batch": [...]} 并行批次
        {"action": "assemble"} 全部完成
        {"action": "feed_more", "message": "..."} 需要更多输入
    """
    session, store, doc = load_session(session_id)

    # 全部完成?
    if session.all_done:
        session.phase = "assembling"
        checkpoint_session(session, store, doc)
        return {
            "action": "assemble",
            "next_hint": f"所有 Section 已完成。下一步: session assemble -s {session_id}",
        }

    # 找到 ready 的 sections (依赖已满足)
    ready = session.ready_sections
    if not ready:
        # 还有 pending 但没有 ready → 可能需要更多输入
        pending = [sid for sid, sp in session.section_progress.items() if sp.status == "pending"]
        if pending:
            return {
                "action": "feed_more",
                "message": f"还有 {len(pending)} 个 Section 等待输入数据",
                "pending_sections": pending,
                "next_hint": f"请补充输入资产，然后: session feed -s {session_id} -i <新输入.json>",
            }
        # 有 in_progress 的 → 等待它们完成
        in_progress = [sid for sid, sp in session.section_progress.items() if sp.status == "generating"]
        return {
            "action": "wait",
            "message": f"等待 {len(in_progress)} 个 Section 生成完成",
            "in_progress": in_progress,
            "next_hint": "等待 --parse 提交结果后，再次执行 session next",
        }

    # 分批: 最多 6 个 Section 并行
    batch = ready[:6]
    if len(batch) == 1:
        return {
            "action": "generate",
            "section_id": batch[0],
            "next_hint": f"下一步: session prompt -s {session_id} --section {batch[0]}",
        }
    return {
        "action": "generate",
        "parallel_batch": batch,
        "next_hint": f"可并行生成 {len(batch)} 个 Section: " + ", ".join(
            f"session prompt -s {session_id} --section {sid}" for sid in batch
        ),
    }


# ═══════════════════════════════════════════════════════════════
#  session prompt (单 Section 生成)
# ═══════════════════════════════════════════════════════════════


def build_section_prompt(
    session_id: str,
    section_id: str,
) -> tuple[str, str]:
    """构建单 Section 的生成 prompt。

    CLI 内部自动从 ContextStore 组装上下文，Agent 不需要管理任何上下文。

    Returns:
        (system_prompt, user_message)
    """
    session, store, doc = load_session(session_id)


    template = load_template(session.template_id)
    if template is None:
        raise ValueError(f"模板不存在: {session.template_id}")

    # 获取 section 标题和结构
    section = doc.find_section(section_id) if doc else None
    section_title = section.title if section else section_id
    section_structure = template.structure_prompt  # 使用完整结构指令

    # 核心: 自动组装上下文（预留输出空间）
    # token_budget 是输入+输出的总预算，输入侧只占 70%，留 30% 给模型生成
    input_budget = int(session.token_budget * 0.7)
    assembled = assemble_section_context(
        store=store,
        section_id=section_id,
        budget=input_budget,
        section_title=section_title,
        section_structure=section_structure,
    )

    system_prompt = _read_prompt("section_generate.md")

    # 组装 user_message
    user_parts = [
        f"## 目标 Section\nID: {section_id}\n标题: {section_title}",
    ]

    # 添加 assembled 上下文
    prompt_text = assembled.to_prompt_text()
    if prompt_text:
        user_parts.append(prompt_text)

    # 标记 section 为 generating（守卫: 已完成的 Section 不可覆盖）
    if section_id in session.section_progress:
        sp = session.section_progress[section_id]
        if sp.status == "done":
            raise ValueError(
                f"Section '{section_id}' 已完成 (status=done)，不能重新生成。"
                f"如需重做，请先删除该 Session 重新初始化。"
            )
        sp.status = "generating"
        sp.attempt_count += 1
        sp.last_attempt_at = now_iso()

    checkpoint_session(session, store, doc)

    return system_prompt, "\n\n".join(user_parts)


def parse_section_result(
    llm_response: str,
    session_id: str,
    section_id: str,
) -> dict:
    """解析 Section 生成结果, 更新 DocumentTree + ContextStore。

    Agent 只看到进度报告。

    Returns:
        {"status": "ok", "section_id": "...", "progress": "12/50"}
    """
    from paper_derived.llm import extract_json

    session, store, doc = load_session(session_id)


    result = extract_json(llm_response)
    new_section = Section.from_dict(result)

    # 更新 DocumentTree
    if doc is not None:
        doc.update_section(section_id, new_section)

    # 更新 section_progress — 域映射: Section.status → SectionProgress.status
    # Section 域: generated | placeholder | empty
    # SectionProgress 域: pending | ready | generating | done | failed
    _STATUS_MAP = {"generated": "done", "placeholder": "done", "empty": "pending"}
    mapped_status = _STATUS_MAP.get(new_section.status, new_section.status)
    if section_id in session.section_progress:
        session.section_progress[section_id].status = mapped_status

    # 写增量 Section 到磁盘
    if doc is not None:
        _write_section_incremental(session_id, section_id, new_section)

    # 更新 phase
    session.phase = "generating"
    checkpoint_session(session, store, doc)

    done = session.done_sections
    total = session.total_sections

    # 构建 next_hint
    if session.all_done:
        hint = f"所有 Section 已完成 ({done}/{total})。下一步: session assemble -s {session_id}"
    else:
        parts = [f"进度 {done}/{total}。"]
        parts.append(f"建议: session summarize -s {session_id} --section {section_id} → session next -s {session_id}")
        hint = " ".join(parts)

    return {
        "status": "ok",
        "section_id": section_id,
        "section_status": new_section.status,
        "progress": f"{done}/{total}",
        "all_done": session.all_done,
        "next_hint": hint,
    }


# ═══════════════════════════════════════════════════════════════
#  session summarize (Section 摘要, 可选)
# ═══════════════════════════════════════════════════════════════


def build_summarize_prompt(
    session_id: str,
    section_id: str,
) -> tuple[str, str]:
    """构建 Section 摘要生成的 prompt。"""
    session, store, doc = load_session(session_id)

    section = doc.find_section(section_id) if doc else None
    if section is None:
        raise ValueError(f"Section 不存在: {section_id}")

    system_prompt = _read_prompt("ctx_summarize.md")
    user_message = f"## Section: {section.title} (ID: {section.id})\n\n{section.content}"
    return system_prompt, user_message


def parse_summarize_result(
    llm_response: str,
    session_id: str,
    section_id: str,
) -> dict:
    """解析 Section 摘要, 存入 ContextStore (Agent 不可见)。

    Returns:
        {"status": "stored", "section_id": "..."}
    """
    from paper_derived.llm import extract_json

    session, store, doc = load_session(session_id)


    result = extract_json(llm_response)

    summary = SectionSummary(
        section_id=section_id,
        title=result.get("title", ""),
        summary=result.get("summary", ""),
        key_entities=result.get("key_entities", []),
        token_count=count_tokens(result.get("summary", "")),
        generated_at=now_iso(),
    )
    store.section_summaries[section_id] = summary

    checkpoint_session(session, store, doc)
    return {
        "status": "stored",
        "section_id": section_id,
        "next_hint": f"摘要已存入上下文库。下一步: session next -s {session_id}",
    }


def session_assemble(session_id: str) -> DocumentTree:
    """组装最终文档: 合并所有 Section, 解析交叉引用。

    无需 LLM (交叉引用解析是确定性的)。

    Returns:
        完整的 DocumentTree
    """
    session, store, doc = load_session(session_id)
    if doc is None:
        raise ValueError(f"Session {session_id} 没有 DocumentTree")

    # 解析 {{ref:section_id}} 占位符
    _resolve_cross_refs(doc)

    session.phase = "complete"
    checkpoint_session(session, store, doc)
    return doc


def _resolve_cross_refs(doc: DocumentTree) -> None:
    """替换 {{ref:section_id}} 为实际章节标题链接。"""
    import re

    pattern = r'\{\{ref:([^}]+)\}\}'

    def replacer(match):
        ref_id = match.group(1)
        ref_section = doc.find_section(ref_id)
        if ref_section:
            return f"[{ref_section.title}](#{ref_id})"
        return match.group(0)  # 未找到则保留原始占位符

    def walk(sections: list[Section]) -> None:
        for s in sections:
            if s.content:
                s.content = re.sub(pattern, replacer, s.content)
            walk(s.children)

    walk(doc.sections)


# ═══════════════════════════════════════════════════════════════
#  session status
# ═══════════════════════════════════════════════════════════════


def session_status(session_id: str) -> dict:
    """查看 Session 状态。无需 LLM。"""
    session, store, doc = load_session(session_id)

    status_counts = {}
    for sp in session.section_progress.values():
        status_counts[sp.status] = status_counts.get(sp.status, 0) + 1

    data_gaps = []
    if store:
        for sid, extraction in store.extraction_map.items():
            if extraction.hint:
                data_gaps.append({"section_id": sid, "hint": extraction.hint})

    return {
        "session_id": session.session_id,
        "template_id": session.template_id,
        "phase": session.phase,
        "sections": status_counts,
        "progress": f"{session.done_sections}/{session.total_sections}",
        "data_gaps": data_gaps,
        "ready_for_generation": session.ready_sections,
        "checkpoint_version": session.checkpoint_version,
    }


# ═══════════════════════════════════════════════════════════════
#  session search
# ═══════════════════════════════════════════════════════════════


def session_search(
    session_id: str,
    query: str,
    focus: str = "",
    budget: int = 2000,
) -> dict:
    """搜索 ContextStore，带 token 预算防护。无需 LLM。

    Args:
        session_id: Session ID
        query: 搜索关键词
        focus: 可选，聚焦到指定 entity_key 获取完整详情
        budget: 返回结果的 token 预算上限（默认 2000）

    Returns:
        搜索结果 dict，带 snippet、related_sections、truncated 标记
    """
    session, store, doc = load_session(session_id)
    if not store.entity_index:
        return {"query": query, "results": [], "total_matches": 0, "hint": "ContextStore 为空，请先 session feed"}

    # ── focus 模式: 返回指定实体的完整详情 ──
    if focus:
        return _search_focus(store, focus, budget)

    # ── 全文搜索 ──
    query_lower = query.lower()
    scored: list[tuple[ContextEntity, float]] = []

    for key, entity in store.entity_index.items():
        score = _match_score(entity, query_lower)
        if score > 0:
            scored.append((entity, score))

    # 也搜索 section summaries
    related_section_ids = set()
    for sid, summary in store.section_summaries.items():
        if query_lower in summary.summary.lower() or query_lower in summary.title.lower():
            related_section_ids.add(sid)

    # 按 score 降序
    scored.sort(key=lambda x: x[1], reverse=True)

    # 在预算内构建结果
    results = []
    used_tokens = 0
    for entity, score in scored:
        snippet = _make_snippet(entity, max_chars=200)
        entry_tokens = count_tokens(snippet)
        if used_tokens + entry_tokens > budget:
            break
        results.append({
            "entity_key": entity.key,
            "kind": entity.kind,
            "name": entity.name,
            "confidence": round(entity.confidence, 2),
            "score": round(score, 2),
            "snippet": snippet,
            "related_sections": entity.related_sections,
        })
        used_tokens += entry_tokens
        related_section_ids.update(entity.related_sections)

    total_matches = len(scored)
    truncated = len(results) < total_matches

    hint = ""
    if truncated:
        focus_keys = [scored[len(results)][0].key] if len(results) < len(scored) else []
        hint = f"还有 {total_matches - len(results)} 个匹配未显示"
        if focus_keys:
            hint += f"。使用 --focus {focus_keys[0]} 获取完整详情"

    return {
        "query": query,
        "results": results,
        "related_sections": sorted(related_section_ids),
        "total_matches": total_matches,
        "shown": len(results),
        "truncated": truncated,
        "hint": hint,
        "next_hint": "继续生成请执行: session next -s " + session_id,
    }


def _search_focus(store: ContextStore, entity_key: str, budget: int) -> dict:
    """聚焦模式: 返回指定实体的完整详情 + raw_fragment。"""
    entity = store.entity_index.get(entity_key)
    if entity is None:
        # 模糊匹配: 尝试 kind:name 格式的部分匹配
        for key, e in store.entity_index.items():
            if entity_key in key or entity_key in e.name:
                entity = e
                break

    if entity is None:
        return {
            "focus": entity_key,
            "results": [],
            "hint": f"未找到实体: {entity_key}",
        }

    # 构建详情
    detail_parts = [f"### {entity.kind}: {entity.name}"]
    if entity.description:
        detail_parts.append(entity.description)
    if entity.attributes:
        for k, v in entity.attributes.items():
            detail_parts.append(f"- {k}: {v}")
    if entity.source_input_id:
        detail_parts.append(f"*来源: {entity.source_input_id}*")

    # 尝试附加 raw_fragment
    fragment_key = entity.raw_fragment_key or entity.key
    fragment = store.raw_fragments.get(fragment_key, "")
    if fragment:
        frag_tokens = count_tokens(fragment)
        remaining = budget - count_tokens("\n".join(detail_parts))
        if frag_tokens <= remaining:
            detail_parts.append(f"\n相关原文:\n{fragment}")
        else:
            # 截断 fragment
            truncated_frag = truncate_to_budget(fragment, remaining - 50)
            detail_parts.append(f"\n相关原文 (截断):\n{truncated_frag}\n⚠️ 原文因 token 预算被截断")

    detail_text = "\n".join(detail_parts)
    actual_tokens = count_tokens(detail_text)

    return {
        "focus": entity_key,
        "entity_key": entity.key,
        "kind": entity.kind,
        "name": entity.name,
        "confidence": round(entity.confidence, 2),
        "detail": detail_text,
        "tokens_used": actual_tokens,
        "budget": budget,
        "has_fragment": bool(fragment),
        "related_sections": entity.related_sections,
        "next_hint": "继续生成请执行: session next",
    }


def _match_score(entity: ContextEntity, query_lower: str) -> float:
    """计算实体与查询的匹配分数。"""
    score = 0.0

    # 名称精确匹配 (最高分)
    if query_lower == entity.name.lower():
        score += 10.0
    elif query_lower in entity.name.lower():
        score += 5.0

    # kind 匹配
    if query_lower in entity.kind.lower():
        score += 3.0

    # description 匹配
    if entity.description and query_lower in entity.description.lower():
        score += 2.0

    # attributes 值匹配
    for v in entity.attributes.values():
        if isinstance(v, str) and query_lower in v.lower():
            score += 1.0
            break

    # 乘以 confidence 加权
    return score * max(entity.confidence, 0.1)


def _make_snippet(entity: ContextEntity, max_chars: int = 200) -> str:
    """生成实体的简短摘要。"""
    parts = []
    if entity.description:
        desc = entity.description
        if len(desc) > max_chars:
            desc = desc[:max_chars - 3] + "..."
        parts.append(desc)
    else:
        # 从 attributes 构建
        attr_items = list(entity.attributes.items())[:3]
        attr_str = ", ".join(f"{k}={v}" for k, v in attr_items)
        if attr_str:
            parts.append(attr_str[:max_chars])

    return parts[0] if parts else f"({entity.kind})"


# ═══════════════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════════════


def _write_section_incremental(session_id: str, section_id: str, section: Section) -> Path | None:
    """写增量 Section .md 文件到 session output 目录。"""
    from paper_derived.session_store import session_dir
    from paper_derived.format_writer import _render_section

    if not section.content or section.status == "empty":
        return None

    output_dir = session_dir(session_id) / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"section-{section_id}.md"
    path = output_dir / filename

    md_text = _render_section(section)
    path.write_text(md_text, encoding="utf-8")
    return path
