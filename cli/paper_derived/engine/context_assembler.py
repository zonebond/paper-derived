"""上下文组装算法 — 按 token 预算自动组装 Section prompt 的上下文.

核心思路:
  不让 Agent 管理上下文。CLI 内部决定每个 Section prompt 包含什么内容。
  严格优先级层, 从预算中逐层扣除:
    Layer 1: Glossary + Style + Validation (始终包含, 可缓存)
    Layer 2: Section Structure (本节结构指令)
    Layer 3: Direct Entities (extraction_map 中的, 按 confidence 降序)
    Layer 4: Raw Fragments (直接实体的相关原文)
    Layer 5: Cross-Section Summaries (entity overlap 评分排序)
    Layer 6: Entity Catalog (热力图降级: 放不下的实体输出 compact 目录)

  热力图降级:
    当 entity 列表因预算不足无法全部详细展示时,
    不是静默 omit, 而是输出一个 compact 的 "entity 目录":
    | 实体 | 类型 | 置信度 |
    | user_id | field | 0.95 |
    | ... (15 more) |
"""

from __future__ import annotations

from paper_derived.models.context import (
    ContextStore,
    ContextEntity,
    SectionExtraction,
    SectionSummary,
    AssembledContext,
)
from paper_derived.engine._tokens import count_tokens, truncate_to_budget


# ── 主入口 ──────────────────────────────────────────────────────


def assemble_section_context(
    store: ContextStore,
    section_id: str,
    budget: int,
    section_title: str = "",
    section_structure: str = "",
) -> AssembledContext:
    """为指定 Section 组装上下文, 严格在 token 预算内.

    Args:
        store: ContextStore 知识库
        section_id: 目标 Section ID
        budget: token 预算 (输入侧, 不含输出 reserve)
        section_title: Section 标题 (用于结构上下文)
        section_structure: Section 的模板结构指令 (可选)

    Returns:
        AssembledContext — 组装好的上下文, 可通过 to_prompt_text() 生成 user_message
    """
    result = AssembledContext(section_id=section_id, budget=budget)
    remaining = budget

    # ── Layer 1: 固定前缀 (glossary + style + validation) ──
    # 逐层截断: validation → style → glossary，保证 remaining >= 0
    glossary_text = _format_glossary(store.glossary)
    style_text = _format_style_rules(store.style_rules)
    validation_text = _format_validation_rules(store.validation_rules)

    # 先尝试完整放入
    prefix_cost = count_tokens(glossary_text + style_text + validation_text)
    if prefix_cost > remaining:
        # 截断 validation
        gs_cost = count_tokens(glossary_text + style_text)
        if gs_cost < remaining:
            validation_text = truncate_to_budget(validation_text, remaining - gs_cost)
        elif count_tokens(glossary_text) < remaining:
            # 连 style 都放不下，截断 style
            style_text = truncate_to_budget(style_text, remaining - count_tokens(glossary_text))
            validation_text = ""
        else:
            # 连 glossary 都放不下，截断 glossary
            glossary_text = truncate_to_budget(glossary_text, remaining)
            style_text = ""
            validation_text = ""

    result.glossary_text = glossary_text
    result.style_guide_text = style_text
    result.validation_rules_text = validation_text
    remaining -= count_tokens(glossary_text + style_text + validation_text)
    remaining = max(remaining, 0)  # 防御性 clamp

    # ── Layer 2: Section 结构 ──
    structure_text = section_structure or _format_section_structure(store, section_id, section_title)
    struct_cost = count_tokens(structure_text)
    if struct_cost <= remaining:
        result.structure_context_text = structure_text
        remaining -= struct_cost

    # ── Layer 3+4: Direct Entities + Raw Fragments ──
    extraction = store.extraction_map.get(section_id)
    direct_keys = extraction.entity_keys if extraction else []

    if direct_keys:
        # 预估 omitted catalog 可能需要的空间 (至少 50 tokens)
        catalog_reserve = min(100, remaining // 4)
        entity_budget = remaining - catalog_reserve

        # 先尝试带 raw fragments 的完整模式
        entity_text, included, omitted = _select_entities_within_budget(
            store, direct_keys, max(entity_budget, 50), include_fragments=True,
        )
        result.entity_context_text = entity_text
        result.omitted_entities = omitted
        remaining -= count_tokens(entity_text)

        # 热力图降级: 如果有 omitted entities, 输出 compact 目录
        if omitted:
            catalog_text = _format_entity_catalog(store, omitted)
            catalog_cost = count_tokens(catalog_text)
            if catalog_cost <= remaining:
                result.entity_catalog_text = catalog_text
                remaining -= catalog_cost
            else:
                # 连完整 catalog 都放不下 → 极简一行提示
                brief = f"⚠️ 另有 {len(omitted)} 个相关实体因 token 预算被省略。"
                if count_tokens(brief) <= remaining:
                    result.entity_catalog_text = brief
                    remaining -= count_tokens(brief)

    # ── Layer 5: Cross-Section Summaries ──
    if remaining > 200 and store.section_summaries:
        related_ids = _find_related_sections(store, section_id)
        if related_ids:
            summary_text, included_ids, omitted_ids = _select_summaries_within_budget(
                store, related_ids, remaining,
            )
            result.summary_context_text = summary_text
            result.omitted_summaries = omitted_ids
            remaining -= count_tokens(summary_text)

    result.total_tokens_used = budget - remaining
    return result


# ── 实体选择 (按 confidence 降序, greedy) ──────────────────────


def _select_entities_within_budget(
    store: ContextStore,
    entity_keys: list[str],
    budget: int,
    include_fragments: bool = True,
) -> tuple[str, list[str], list[str]]:
    """选择在预算内的实体, 按 confidence 降序.

    Returns:
        (formatted_text, included_keys, omitted_keys)
    """
    # 收集并按 confidence 排序
    entities = []
    for key in entity_keys:
        entity = store.entity_index.get(key)
        if entity:
            entities.append(entity)
    entities.sort(key=lambda e: e.confidence, reverse=True)

    included: list[str] = []
    omitted: list[str] = []
    parts: list[str] = []
    used = 0

    for entity in entities:
        # 实体描述
        entry = _format_entity(entity)
        entry_cost = count_tokens(entry)

        # 可选: raw fragment
        frag_cost = 0
        fragment = ""
        if include_fragments and entity.raw_fragment_key:
            fragment = store.raw_fragments.get(entity.raw_fragment_key, "")
            if fragment:
                frag_text = f"\n相关原文:\n{fragment}"
                frag_cost = count_tokens(frag_text)

        total_cost = entry_cost + frag_cost
        if used + total_cost <= budget:
            parts.append(entry)
            if fragment:
                parts.append(frag_text)
            included.append(entity.key)
            used += total_cost
        else:
            omitted.append(entity.key)

    return "\n\n".join(parts), included, omitted


# ── 摘要选择 (按 entity overlap 评分排序) ──────────────────────


def _select_summaries_within_budget(
    store: ContextStore,
    section_ids: list[str],
    budget: int,
) -> tuple[str, list[str], list[str]]:
    """选择在预算内的 Section 摘要.

    Returns:
        (formatted_text, included_ids, omitted_ids)
    """
    included: list[str] = []
    omitted: list[str] = []
    parts: list[str] = []
    used = 0

    for sid in section_ids:
        summary = store.section_summaries.get(sid)
        if not summary:
            continue
        text = _format_section_summary(summary)
        tokens = count_tokens(text)
        if used + tokens <= budget:
            parts.append(text)
            included.append(sid)
            used += tokens
        else:
            omitted.append(sid)

    return "\n\n".join(parts), included, omitted


def _find_related_sections(store: ContextStore, section_id: str) -> list[str]:
    """找到与当前 Section 有 entity 重叠的已完成 Section.

    评分: overlap_score = |entities(S) ∩ entities(current)| / |entities(current)|
    按 score 降序排列。
    """
    extraction = store.extraction_map.get(section_id)
    if not extraction or not extraction.entity_keys:
        return []

    my_entity_set = set(extraction.entity_keys)
    scored: list[tuple[str, float]] = []

    for sid, summary in store.section_summaries.items():
        if sid == section_id:
            continue
        overlap = len(set(summary.key_entities) & my_entity_set)
        if overlap > 0:
            score = overlap / max(len(my_entity_set), 1)
            scored.append((sid, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [sid for sid, _ in scored]


# ── 格式化辅助 ──────────────────────────────────────────────────


def _format_glossary(glossary: dict[str, str]) -> str:
    """格式化术语表."""
    if not glossary:
        return ""
    lines = []
    for term, definition in glossary.items():
        lines.append(f"- **{term}**: {definition}")
    return "\n".join(lines)


def _format_style_rules(rules: list[str]) -> str:
    """格式化风格规则."""
    if not rules:
        return ""
    return "\n".join(f"- {r}" for r in rules)


def _format_validation_rules(rules: list[str]) -> str:
    """格式化校验规则."""
    if not rules:
        return ""
    return "\n".join(f"- [校验] {r}" for r in rules)


def _format_section_structure(store: ContextStore, section_id: str, title: str = "") -> str:
    """格式化 Section 结构指令."""
    parts = [f"目标 Section: {section_id}"]
    if title:
        parts.append(f"标题: {title}")

    # 从 extraction_map 取 hint
    extraction = store.extraction_map.get(section_id)
    if extraction and extraction.hint:
        parts.append(f"数据缺口提示: {extraction.hint}")

    return "\n".join(parts)


def _format_entity(entity: ContextEntity) -> str:
    """格式化单个实体的详细描述."""
    lines = [f"### {entity.kind}: {entity.name}"]
    if entity.description:
        lines.append(entity.description)
    if entity.attributes:
        for k, v in entity.attributes.items():
            lines.append(f"- {k}: {v}")
    if entity.source_input_id:
        lines.append(f"*来源: {entity.source_input_id}*")
    return "\n".join(lines)


def _format_entity_catalog(store: ContextStore, omitted_keys: list[str]) -> str:
    """格式化热力图降级: 因预算不足被压缩为目录的实体列表."""
    lines = [
        f"⚠️ 以下 {len(omitted_keys)} 个实体因 token 预算不足被压缩为目录:",
        "",
        "| 实体 | 类型 | 置信度 |",
        "|------|------|--------|",
    ]
    for key in omitted_keys[:20]:  # 目录最多 20 行
        entity = store.entity_index.get(key)
        if entity:
            lines.append(f"| {entity.name} | {entity.kind} | {entity.confidence:.0%} |")
    if len(omitted_keys) > 20:
        lines.append(f"| ... | ... | ... (还有 {len(omitted_keys) - 20} 个) |")
    return "\n".join(lines)


def _format_section_summary(summary: SectionSummary) -> str:
    """格式化单个 Section 的摘要."""
    parts = [f"**{summary.title}** (Section: {summary.section_id})"]
    if summary.summary:
        parts.append(summary.summary)
    return "\n".join(parts)
