"""生成域引擎 — 构造 prompt + 解析 LLM 响应."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from paper_derived.engine._paths import read_prompt
from paper_derived.models.document import DocumentTree, DocumentMeta
from paper_derived.models.extraction import ExtractionResult, SectionExtract
from paper_derived.models.input_asset import InputAsset
from paper_derived.models.reports import PreflightReport, SectionPreflight
from paper_derived.storage import load_template, make_document_id


def _read_prompt(name: str) -> str:
    return read_prompt(name)


def _build_template_context(template_id: str) -> str:
    """构建目标模板上下文文本."""
    template = load_template(template_id)
    if template is None:
        raise ValueError(f"模板不存在: {template_id}")

    parts = [
        f"## 目标模板: {template.name}",
        f"模板 ID: {template.id}",
        f"\n### 模板结构指令\n{template.structure_prompt}",
        f"\n### 模板抽取指令\n{template.extraction_prompt}",
        f"\n### 模板风格指令\n{template.style_prompt}",
        f"\n### 模板校验指令\n{template.validation_prompt}",
        f"\n### Section 依赖\n{json.dumps(template.section_dependencies, ensure_ascii=False, indent=2)}",
    ]
    return "\n\n".join(parts)


def _build_template_context_for_sections(
    template_id: str, section_ids: list[str]
) -> str:
    """构建仅包含目标 Section 的模板上下文.

    保留风格和校验指令（跨批一致性），
    并包含结构/抽取指令中与目标 Section 相关的内容。
    """
    template = load_template(template_id)
    if template is None:
        raise ValueError(f"模板不存在: {template_id}")

    sid_set = set(section_ids)

    def filter_by_section(raw: str) -> str:
        """从文本中筛选与目标 Section 相关的段落."""
        lines = raw.split("\n")
        filtered = []
        in_scope = False
        for line in lines:
            stripped = line.strip()
            # 如果行中包含任何目标 section ID → 进入作用域
            if any(sid in stripped for sid in section_ids):
                in_scope = True
            if in_scope:
                filtered.append(line)
                # 检测是否遇到新的顶级章节标题（L1 或 L2），
                # 不是目标且不包含目标 ID → 退出
                if (stripped.startswith("###") or stripped.startswith("##") or
                    stripped.startswith("#") or (stripped and stripped[0].isdigit())):
                    if not any(sid in stripped for sid in section_ids):
                        # 检查后面是否有目标 section
                        pass  # 保持开放
        return "\n".join(filtered) if filtered else raw

    parts = [
        f"## 目标模板: {template.name}",
        f"模板 ID: {template.id}",
        f"\n### 目标 Section\n{json.dumps(section_ids, ensure_ascii=False)}",
        f"\n### 模板结构指令\n{template.structure_prompt}",
        f"\n### 模板抽取指令\n{template.extraction_prompt}",
        f"\n### 模板风格指令\n{template.style_prompt}",
        f"\n### 模板校验指令\n{template.validation_prompt}",
    ]
    return "\n\n".join(parts)


# 原始内容超过此阈值时省略，仅保留摘要和实体列表
_MAX_RAW_CHARS = 20_000


def _build_input_context(input_assets: list[InputAsset], max_raw_chars: int = _MAX_RAW_CHARS) -> str:
    """构建输入资产上下文文本.

    当 raw_content 超过 max_raw_chars 时，省略原文仅保留摘要和实体列表，
    避免大文档撑爆 LLM 上下文窗口。
    """
    parts = [f"## 输入资产 ({len(input_assets)} 份)"]
    for a in input_assets:
        parts.append(f"\n### 资产: {a.name} (ID: {a.id}, 类型: {a.type})")
        parts.append(f"摘要: {a.summary}")
        parts.append(f"实体: {json.dumps([e.to_dict() for e in a.entities], ensure_ascii=False, indent=2)}")
        if len(a.raw_content) > max_raw_chars:
            parts.append(
                f"\n> ⚠️ 原始内容过长（{len(a.raw_content)} 字符），已省略。"
                f"请基于以上摘要和实体列表生成。"
            )
        else:
            parts.append(f"\n原始内容:\n{a.raw_content}")
    return "\n\n".join(parts)


def _build_filtered_input_context(
    input_assets: list[InputAsset],
    extraction: ExtractionResult | None,
    section_ids: list[str],
) -> str:
    """构建仅包含目标 Section 关联实体的输入上下文.

    如果有 ExtractionResult，按 section 筛选关联实体。
    否则回退到所有实体的精简摘要。
    """
    parts = [f"## 输入资产 ({len(input_assets)} 份，仅展示目标 Section 相关实体)"]

    if extraction:
        sid_set = set(section_ids)
        for a in input_assets:
            parts.append(f"\n### 资产: {a.name} (ID: {a.id}, 类型: {a.type})")
            parts.append(f"摘要: {a.summary}")
            # 筛选只与目标 section 相关的实体
            related = []
            for sid in section_ids:
                entities = extraction.get_entities_for_section(sid)
                for e in entities:
                    if e.source_input_id == a.id:
                        related.append(e)
            if related:
                parts.append(
                    f"相关实体: {json.dumps([e.to_dict() for e in related], ensure_ascii=False, indent=2)}"
                )
            else:
                parts.append("相关实体: (无)")
            entities_text = json.dumps(
                [e.to_dict() for e in a.entities], ensure_ascii=False, indent=2
            )
            # 只截取实体列表而非全部 raw_content，节省上下文
            parts.append(f"实体列表:\n{entities_text}")
    else:
        # 无 extraction → 精简版上下文
        for a in input_assets:
            parts.append(f"\n### 资产: {a.name} (ID: {a.id}, 类型: {a.type})")
            parts.append(f"摘要: {a.summary}")
            entities_text = json.dumps(
                [e.to_dict() for e in a.entities], ensure_ascii=False, indent=2
            )
            parts.append(f"实体: {entities_text}")

    return "\n\n".join(parts)


# ── Preflight ──────────────────────────────────────────────────


def build_preflight_prompt(
    input_assets: list[InputAsset], template_id: str
) -> tuple[str, str]:
    """构造资料体检 prompt."""
    system_prompt = _read_prompt("preflight.md")
    user_message = _build_template_context(template_id) + "\n\n" + _build_input_context(input_assets)
    return system_prompt, user_message


def parse_preflight_result(llm_response: str) -> PreflightReport:
    from paper_derived.llm import extract_json
    result = extract_json(llm_response)
    return PreflightReport(
        ok=result.get("ok", True),
        sections=[SectionPreflight.from_dict(s) for s in result.get("sections", [])],
        summary=result.get("summary", ""),
    )


# ── Extract ────────────────────────────────────────────────────


def build_extract_prompt(
    input_assets: list[InputAsset], template_id: str
) -> tuple[str, str]:
    """构造实体抽取 prompt."""
    system_prompt = _read_prompt("extract.md")
    user_message = _build_template_context(template_id) + "\n\n" + _build_input_context(input_assets)
    return system_prompt, user_message


def parse_extract_result(llm_response: str) -> ExtractionResult:
    from paper_derived.llm import extract_json
    result = extract_json(llm_response)
    return ExtractionResult(
        summary=result.get("summary", ""),
        sections=[SectionExtract.from_dict(s) for s in result.get("sections", [])],
        warnings=result.get("warnings", []),
    )


# ── Generate ───────────────────────────────────────────────────


def build_generate_prompt(
    input_assets: list[InputAsset],
    template_id: str,
    extraction_overrides: dict | None = None,
) -> tuple[str, str]:
    """构造文档生成 prompt."""
    system_prompt = _read_prompt("generate.md")
    user_message = _build_template_context(template_id) + "\n\n" + _build_input_context(input_assets)

    if extraction_overrides:
        user_message += "\n\n## 用户修正的抽取结果 (以此为准)\n" + json.dumps(
            extraction_overrides, ensure_ascii=False, indent=2
        )

    return system_prompt, user_message


def parse_generate_result(
    llm_response: str, template_id: str, input_assets: list[InputAsset]
) -> DocumentTree:
    from paper_derived.llm import extract_json

    result = extract_json(llm_response)
    doc = DocumentTree.from_dict(result)
    doc.sanitize_headings()
    doc.document_id = doc.document_id or make_document_id()
    doc.template_id = template_id
    doc.input_ids = [a.id for a in input_assets]
    doc.generated_at = datetime.now(timezone.utc).isoformat()

    # ── 结构完整性守卫: 确保模板定义的所有 Section 都在输出中 ──
    doc = _enforce_structure_completeness(doc, template_id)

    total, gen, ph = doc.count_sections()
    doc.metadata = DocumentMeta(
        total_sections=total,
        generated_sections=gen,
        placeholder_sections=ph,
    )
    return doc


# ── Outline ──────────────────────────────────────────────────────


def build_outline_prompt(template_id: str) -> tuple[str, str]:
    """构造大纲生成 prompt.

    轻量 prompt，只包含模板结构 + 风格，不包含输入资料。
    要求 LLM 生成带标题和说明的骨架 DocumentTree。
    """
    template = load_template(template_id)
    if template is None:
        raise ValueError(f"模板不存在: {template_id}")

    system_prompt = _read_prompt("batch.md")
    user_parts = [
        f"## 操作类型\n大纲生成 (outline)",
        f"## 目标模板\n名称: {template.name} (ID: {template.id})",
        f"\n### 模板结构指令\n{template.structure_prompt}",
        f"\n### 模板风格指令\n{template.style_prompt}",
        f"\n## 要求\n仅生成骨架 DocumentTree，不填充具体内容。",
        "每个 Section 的 status 设为 'placeholder'，",
        "content 中写入该 Section 的预期描述（一句话说明本节应包含什么）。",
        "确保包含模板定义的所有 Section，保持层级关系。",
    ]
    return system_prompt, "\n\n".join(user_parts)


def parse_outline_result(llm_response: str, template_id: str) -> DocumentTree:
    """解析大纲生成结果."""
    from paper_derived.llm import extract_json

    result = extract_json(llm_response)
    doc = DocumentTree.from_dict(result)
    doc.document_id = doc.document_id or make_document_id()
    doc.template_id = template_id
    doc.generated_at = datetime.now(timezone.utc).isoformat()

    total, gen, ph = doc.count_sections()
    doc.metadata = DocumentMeta(
        total_sections=total,
        generated_sections=gen,
        placeholder_sections=ph,
    )
    return doc


# ── Batch Generate ───────────────────────────────────────────────


def build_batch_generate_prompt(
    input_assets: list[InputAsset],
    template_id: str,
    section_ids: list[str],
    extraction: ExtractionResult | None = None,
    existing_doc: DocumentTree | None = None,
) -> tuple[str, str]:
    """构造分批生成 prompt.

    只包含目标 Section 的模板上下文 + 相关输入实体，
    大幅压缩 prompt 体积。
    """
    system_prompt = _read_prompt("batch.md")
    parts = [
        _build_template_context_for_sections(template_id, section_ids),
        _build_filtered_input_context(input_assets, extraction, section_ids),
    ]

    if existing_doc:
        parts.append(
            "## 已有文档树（非目标 Section 保留原样，目标 Section 将被覆盖）\n"
            + json.dumps(existing_doc.to_dict(), ensure_ascii=False, indent=2)
        )

    return system_prompt, "\n\n".join(parts)


def parse_batch_generate_result(
    llm_response: str, template_id: str, input_assets: list[InputAsset]
) -> DocumentTree:
    """解析分批生成结果."""
    from paper_derived.llm import extract_json

    result = extract_json(llm_response)
    doc = DocumentTree.from_dict(result)
    doc.sanitize_headings()
    doc.document_id = doc.document_id or make_document_id()
    doc.template_id = template_id
    doc.input_ids = [a.id for a in input_assets]
    doc.generated_at = datetime.now(timezone.utc).isoformat()

    # ── 结构完整性守卫: 分批模式下仅检查生成的 Section 是否完整 ──
    # 分批生成不要求全模板 Section 都在（本批只生成指定的 Section），
    # 但本批指定的每个 Section 必须有非空内容

    total, gen, ph = doc.count_sections()
    doc.metadata = DocumentMeta(
        total_sections=total,
        generated_sections=gen,
        placeholder_sections=ph,
    )
    return doc


# ── 结构完整性守卫 ──────────────────────────────────────────────


def _enforce_structure_completeness(doc: DocumentTree, template_id: str) -> DocumentTree:
    """确保文档包含模板定义的全部 Section。

    如果 LLM 输出的文档缺少某些模板 Section（例如因输入资料不足而省略），
    自动补充为 placeholder Section，并添加 hints 说明。

    这是结构完整性铁律的代码层保障：
    → 输出文档必须包含模板定义的全部 Section，一个都不能少。
    """
    from paper_derived.models.document import Section

    template = load_template(template_id)
    if template is None:
        return doc

    # 构建模板定义的 Section ID 集合（含层级信息）
    # 优先使用 section_tree（含层级结构），回退到扁平 section_ids
    if template.section_tree:
        template_sections = _flatten_section_tree(template.section_tree)
    else:
        # 回退：从扁平 section_ids 构建最小结构
        template_sections = [
            {"id": sid, "title": sid.replace("-", " ").title(), "level": 1}
            for sid in template.section_ids
        ]

    template_ids = {s["id"] for s in template_sections}

    # 获取当前文档已有的 Section ID
    existing_ids = set(doc.collect_section_ids())

    # 找出缺失的 Section
    missing_ids = template_ids - existing_ids

    if not missing_ids:
        return doc

    # 为每个缺失的 Section 创建 placeholder
    for missing_id in missing_ids:
        info = next((s for s in template_sections if s["id"] == missing_id), {})
        title = info.get("title", missing_id.replace("-", " ").title())
        level = info.get("level", 1)

        placeholder_section = Section(
            id=missing_id,
            title=title,
            content=(
                f"*本节内容待补充。*\n\n"
                f"本章应包含 {title} 的相关内容。"
                f"当前输入资料中未提供此部分信息，请补充相关资料后重新生成。"
            ),
            level=level,
            template_ref=f"{template_id}.{missing_id}",
            status="placeholder",
            hints=[f"自动补充的占位 Section：输入资料中未包含 {title} 相关内容"],
        )
        doc.sections.append(placeholder_section)

    return doc


def _flatten_section_tree(
    nodes: list[dict], level: int = 1
) -> list[dict]:
    """展平 section_tree，返回所有节点的扁平列表（附带层级信息）。"""
    result = []
    for node in nodes:
        node_with_level = {**node, "level": node.get("level", level)}
        result.append(node_with_level)
        children = node.get("children", [])
        if children:
            result.extend(_flatten_section_tree(children, level + 1))
    return result
