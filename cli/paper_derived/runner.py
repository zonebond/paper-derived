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
