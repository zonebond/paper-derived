"""校验域引擎 — 构造 prompt + 解析 LLM 响应."""

from __future__ import annotations

import json

from paper_derived.engine._paths import read_prompt
from paper_derived.models.document import DocumentTree
from paper_derived.models.reports import ValidationReport, ValidationCheckpoint
from paper_derived.storage import load_template


def _read_prompt(name: str) -> str:
    return read_prompt(name)


def build_validate_prompt(doc: DocumentTree, template_id: str) -> tuple[str, str]:
    """构造质检 prompt."""
    template = load_template(template_id)
    if template is None:
        raise ValueError(f"模板不存在: {template_id}")

    system_prompt = _read_prompt("validate.md")
    user_message = f"""## 目标模板校验指令
{template.validation_prompt}

## 模板结构指令
{template.structure_prompt}

## 待校验文档
{json.dumps(doc.to_dict(), ensure_ascii=False, indent=2)}
"""
    return system_prompt, user_message


def parse_validate_result(llm_response: str) -> ValidationReport:
    from paper_derived.llm import extract_json
    result = extract_json(llm_response)
    return ValidationReport(
        passed=result.get("passed", True),
        total_checkpoints=result.get("total_checkpoints", 0),
        passed_count=result.get("passed_count", 0),
        failed_count=result.get("failed_count", 0),
        checkpoints=[ValidationCheckpoint.from_dict(c) for c in result.get("checkpoints", [])],
        summary=result.get("summary", ""),
    )
