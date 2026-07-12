"""模板域引擎 — 构造 prompt + 解析 LLM 响应.

引擎不调 LLM。调用方 (Agent) 负责:
1. 调 build_register_template_prompt() 拿 prompt
2. 用自己的 LLM 执行
3. 调 parse_register_template_result() 解析结果
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from paper_derived.engine._paths import PROMPTS_DIR
from paper_derived.models.template import Template, TemplateSummary
from paper_derived.storage import save_template, load_template, list_all_templates


def _read_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


# ── Prompt builders ────────────────────────────────────────────


def build_register_template_prompt(sample_text: str, name: str, description: str = "") -> tuple[str, str]:
    """构造模板注册 prompt.

    Returns:
        (system_prompt, user_message)
    """
    system_prompt = _read_prompt("register_template.md")
    user_message = sample_text
    return system_prompt, user_message


def build_update_template_prompt(sample_text: str, existing_template: Template) -> tuple[str, str]:
    """构造模板更新 prompt.

    Returns:
        (system_prompt, user_message)
    """
    system_prompt = _read_prompt("register_template.md")
    user_message = f"""## 当前模板 (需在保持结构的前提下更新内容)

{json.dumps(existing_template.to_dict(), ensure_ascii=False, indent=2)}

## 新的样例文档

{sample_text}
"""
    return system_prompt, user_message


# ── Result parsers ─────────────────────────────────────────────


def parse_register_template_result(llm_response: str, name: str, description: str = "") -> Template:
    """解析 LLM 响应，构建 Template 对象并保存."""
    from paper_derived.llm import extract_json

    result = extract_json(llm_response)
    now = datetime.now(timezone.utc).isoformat()

    template = Template(
        id=_to_kebab_case(result.get("id", name)),
        name=result.get("name", name),
        description=result.get("description", description),
        extraction_prompt=result.get("extraction_prompt", ""),
        structure_prompt=result.get("structure_prompt", ""),
        style_prompt=result.get("style_prompt", ""),
        validation_prompt=result.get("validation_prompt", ""),
        section_ids=_extract_section_ids(result.get("sections", [])),
        section_dependencies=_extract_dependencies(result.get("sections", [])),
        section_tree=result.get("sections", []),
        created_at=now,
        updated_at=now,
    )

    save_template(template)
    return template


def parse_update_template_result(
    llm_response: str, existing: Template, description: str = ""
) -> Template:
    """解析更新结果，合并到已有模板."""
    from paper_derived.llm import extract_json

    result = extract_json(llm_response)
    now = datetime.now(timezone.utc).isoformat()

    existing.extraction_prompt = result.get("extraction_prompt", existing.extraction_prompt)
    existing.structure_prompt = result.get("structure_prompt", existing.structure_prompt)
    existing.style_prompt = result.get("style_prompt", existing.style_prompt)
    existing.validation_prompt = result.get("validation_prompt", existing.validation_prompt)
    existing.section_ids = _extract_section_ids(result.get("sections", []))
    existing.section_dependencies = _extract_dependencies(result.get("sections", []))
    existing.section_tree = result.get("sections", [])
    existing.description = description or existing.description
    existing.version += 1
    existing.updated_at = now

    save_template(existing)
    return existing


# ── 不需要 LLM 的操作 ──────────────────────────────────────────


def get_template(template_id: str) -> Template | None:
    return load_template(template_id)


def list_all() -> list[dict]:
    return [t.to_dict() for t in list_all_templates()]


# ── Helpers ────────────────────────────────────────────────────


def _to_kebab_case(s: str) -> str:
    """将字符串转换为 kebab-case.

    非字母数字字符替换为连字符，合并连续连字符，去除首尾连字符。
    空字符串返回 "template" 作为兜底。
    """
    import re
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s.lower() if s else "template"


def _extract_section_ids(sections: list[dict]) -> list[str]:
    ids = []
    for s in sections:
        if isinstance(s, str):
            ids.append(s)
            continue
        if "id" in s:
            ids.append(s["id"])
        children = s.get("children", [])
        if children and isinstance(children[0], dict):
            ids.extend(_extract_section_ids(children))
        elif children and isinstance(children[0], str):
            ids.extend(children)
    return ids


def _extract_dependencies(sections: list[dict]) -> dict:
    deps = {}
    def walk(secs):
        for s in secs:
            if isinstance(s, str):
                continue
            dep = s.get("dependency", {})
            if dep:
                deps[s["id"]] = dep
            children = s.get("children", [])
            if children and isinstance(children[0], dict):
                walk(children)
    walk(sections)
    return deps
