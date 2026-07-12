"""输入资产域引擎 — 构造 prompt + 解析 LLM 响应."""

from __future__ import annotations

from datetime import datetime, timezone

from paper_derived.engine._paths import PROMPTS_DIR
from paper_derived.models.input_asset import InputAsset, Entity


def _read_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def build_register_input_prompt(raw_text: str, name: str) -> tuple[str, str]:
    """构造输入资产注册 prompt.

    Returns:
        (system_prompt, user_message)
    """
    system_prompt = _read_prompt("register_input.md")
    user_message = raw_text
    return system_prompt, user_message


def build_register_input_chunk_prompt(
    chunk_text: str,
    name: str,
    chunk_index: int,
    total_chunks: int,
) -> tuple[str, str]:
    """构造分块注册 prompt.

    在 system prompt 中追加分块上下文，让 LLM 知道自己只看到文档的一部分。
    user message 只包含当前块的文本。

    Returns:
        (system_prompt, user_message)
    """
    base_prompt = _read_prompt("register_input.md")
    chunk_context = (
        f"\n\n## 分块说明\n"
        f"本文档已被分为 {total_chunks} 块，你正在处理第 {chunk_index + 1} 块。\n"
        f"请仅从当前块中提取实体，不要推测其他块的内容。\n"
        f"如果当前块是文档的开头，请尝试识别文档的整体类型和主题。\n"
    )
    system_prompt = base_prompt + chunk_context
    user_message = chunk_text
    return system_prompt, user_message


def parse_register_input_result(llm_response: str, raw_text: str, name: str, source: str = "", slim: bool = False) -> InputAsset:
    """解析 LLM 响应，构建 InputAsset.

    Args:
        slim: 为 True 时，raw_content 置空，仅保留摘要和实体。
              适用于大文档，避免 InputAsset JSON 过大。
    """
    from paper_derived.llm import extract_json

    result = extract_json(llm_response)
    now = datetime.now(timezone.utc).isoformat()

    return InputAsset(
        id=result.get("id", name),
        name=result.get("name", name),
        type=result.get("type", "plain_text"),
        raw_content="" if slim else raw_text,
        summary=result.get("summary", ""),
        entities=[
            Entity(
                kind=e.get("kind", ""),
                name=e.get("name", ""),
                description=e.get("description", ""),
                location=e.get("location", ""),
            )
            for e in result.get("entities", [])
        ],
        metadata={"source": source, "registered_at": now, "slim": slim},
    )


def merge_input_assets(
    partial_assets: list[InputAsset],
    raw_text: str,
    name: str,
    source: str = "",
    slim: bool = False,
) -> InputAsset:
    """将分块注册的多个局部 InputAsset 合并为一个完整的 InputAsset.

    策略:
    - id/name/type: 取第一个非空值
    - summary: 合并所有 summary，去重
    - entities: 合并所有实体，按 (kind, name) 去重
    - raw_content: slim 模式下置空，否则使用完整原文
    - metadata: 合并，记录合并来源

    Args:
        slim: 为 True 时，raw_content 置空，仅保留摘要和实体。
    """
    if not partial_assets:
        raise ValueError("至少需要一个局部 InputAsset")

    # 取第一个非空的 id / name / type
    first = partial_assets[0]
    merged_id = first.id or name
    merged_name = first.name or name
    merged_type = first.type or "plain_text"

    # 合并 summary：拼接所有非空 summary
    summaries = [a.summary for a in partial_assets if a.summary]
    merged_summary = "；".join(summaries) if summaries else ""

    # 合并 entities：按 (kind, name) 去重，保留最详细的描述
    seen: dict[tuple[str, str], Entity] = {}
    for a in partial_assets:
        for e in a.entities:
            key = (e.kind, e.name)
            if key not in seen or len(e.description) > len(seen[key].description):
                seen[key] = e
    merged_entities = list(seen.values())

    now = datetime.now(timezone.utc).isoformat()
    merged_meta = {
        "source": source,
        "registered_at": now,
        "merged_from_chunks": len(partial_assets),
        "slim": slim,
    }

    return InputAsset(
        id=merged_id,
        name=merged_name,
        type=merged_type,
        raw_content="" if slim else raw_text,
        summary=merged_summary,
        entities=merged_entities,
        metadata=merged_meta,
    )
