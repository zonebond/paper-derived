"""文档操作域引擎 — 构造 prompt + 解析 LLM 响应."""

from __future__ import annotations

import json

from paper_derived.engine._paths import read_prompt
from paper_derived.models.document import DocumentTree


def _read_prompt(name: str) -> str:
    return read_prompt(name)


def build_revise_section_prompt(
    doc: DocumentTree, section_id: str, instruction: str
) -> tuple[str, str]:
    """构造局部修改 prompt."""
    section = doc.find_section(section_id)
    system_prompt = _read_prompt("revise.md")
    user_message = f"""## 操作类型
局部修改 (revise_section)

## 目标 Section
ID: {section_id}
当前内容:
```markdown
{section.content if section else "(Section 不存在)"}
```

## 修改指令
{instruction}

## 完整文档树 (仅目标 Section 需要修改，其余保持不变)
{json.dumps(doc.to_dict(), ensure_ascii=False, indent=2)}
"""
    return system_prompt, user_message


def build_revise_global_prompt(doc: DocumentTree, instruction: str) -> tuple[str, str]:
    """构造全局改写 prompt."""
    system_prompt = _read_prompt("revise.md")
    user_message = f"""## 操作类型
全局改写 (revise_global)

## 修改指令
{instruction}

## 完整文档树
{json.dumps(doc.to_dict(), ensure_ascii=False, indent=2)}
"""
    return system_prompt, user_message


def build_add_section_prompt(
    doc: DocumentTree, parent_id: str | None, section_type: str, hint: str = ""
) -> tuple[str, str]:
    """构造新增 Section prompt."""
    system_prompt = _read_prompt("revise.md")
    user_message = f"""## 操作类型
新增 Section (add_section)

## 目标
父 Section ID: {parent_id or "(根级)"}
Section 类型: {section_type}
提示: {hint or "无"}

## 完整文档树
{json.dumps(doc.to_dict(), ensure_ascii=False, indent=2)}
"""
    return system_prompt, user_message


def build_remove_section_prompt(doc: DocumentTree, section_id: str) -> tuple[str, str]:
    """构造删除 Section prompt."""
    system_prompt = _read_prompt("revise.md")
    user_message = f"""## 操作类型
删除 Section (remove_section)

## 目标
要删除的 Section ID: {section_id}

## 完整文档树
{json.dumps(doc.to_dict(), ensure_ascii=False, indent=2)}
"""
    return system_prompt, user_message


# ── Parsers ────────────────────────────────────────────────────


def parse_revise_result(llm_response: str) -> DocumentTree:
    from paper_derived.llm import extract_json
    result = extract_json(llm_response)
    return DocumentTree.from_dict(result)
