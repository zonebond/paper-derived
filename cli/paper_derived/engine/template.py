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

from paper_derived.engine._paths import read_prompt
from paper_derived.models.template import Template, TemplateSummary
from paper_derived.storage import save_template, load_template, list_all_templates


def _read_prompt(name: str) -> str:
    return read_prompt(name)


# ── Prompt builders ────────────────────────────────────────────


def build_register_template_prompt(sample_text: str, name: str, description: str = "") -> tuple[str, str]:
    """构造模板注册 prompt.

    Returns:
        (system_prompt, user_message)
    """
    system_prompt = _read_prompt("register_template.md")
    user_message = _with_anchor_block(sample_text)
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

{_with_anchor_block(sample_text)}
"""
    return system_prompt, user_message


# ── Result parsers ─────────────────────────────────────────────


def parse_register_template_result(
    llm_response: str, name: str, description: str = "", sample_text: str = ""
) -> Template:
    """解析 LLM 响应，构建 Template 对象并保存.

    提供 sample_text 时执行结构完整性守卫：对照确定性预扫描的一级章节
    锚点，LLM 遗漏的章节自动补回骨架（补回清单挂在返回对象的
    auto_added_sections 属性上）。
    """
    from paper_derived.llm import extract_json

    result = extract_json(llm_response)
    now = datetime.now(timezone.utc).isoformat()

    sections = result.get("sections", [])
    auto_added = _guard_missing_anchors(sections, sample_text) if sample_text else []
    result["sections"] = sections

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
    template.auto_added_sections = auto_added  # 动态属性，供 CLI 报告
    return template


def parse_update_template_result(
    llm_response: str, existing: Template, description: str = "", sample_text: str = ""
) -> Template:
    """解析更新结果，合并到已有模板."""
    from paper_derived.llm import extract_json

    result = extract_json(llm_response)
    now = datetime.now(timezone.utc).isoformat()

    sections = result.get("sections", [])
    auto_added = _guard_missing_anchors(sections, sample_text) if sample_text else []
    result["sections"] = sections
    existing.auto_added_sections = auto_added

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

# ── 结构预扫描（确定性一级章节锚点）────────────────────────────
#
# 目的：治本「文档末尾低密度章节被 LLM 遗漏」。不依赖 LLM 自觉：
# ① build 时把扫描出的锚点注入 prompt，要求逐一覆盖；
# ② parse 后对照锚点，缺失章节自动补回骨架并在结果中报告。

import re as _re

_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _cn_to_int(s: str) -> int | None:
    if s.isdigit():
        return int(s)
    if not s or any(ch not in _CN_NUM for ch in s):
        return None
    if len(s) == 1:
        return _CN_NUM[s]
    if "十" in s:  # 十三 / 二十 / 二十三
        left, _, right = s.partition("十")
        return (_CN_NUM.get(left, 1) if left else 1) * 10 + (_CN_NUM.get(right, 0) if right else 0)
    return None


def _with_anchor_block(sample_text: str) -> str:
    """样例文档前注入确定性锚点清单，强制 LLM 逐一覆盖（含末尾低密度章节）."""
    anchors = scan_top_headings(sample_text)
    if len(anchors) < 2:
        return sample_text
    block = "\n".join(f"{a['number']} {a['title']}" for a in anchors)
    return (
        "## 结构预扫描锚点（确定性提取的一级章节清单）\n"
        "以下章节从样例文档中确定性扫描得出。你输出的 sections 必须逐一覆盖每个锚点"
        "（层级与子节由你分析补充），**禁止遗漏任何一项**——尤其是文档末尾内容稀薄的章节"
        "（如仅一句提示的「注释」、仅一张示例表的「附表」），它们是独立章节，不是附录尾巴。\n\n"
        + block
        + "\n\n## 样例文档全文\n\n"
        + sample_text
    )


def scan_top_headings(text: str) -> list[dict]:
    """确定性扫描一级章节标题，返回 [{"number": "6", "title": "注释"}, ...]。

    识别两类编号标题（行首、短行、非句子）：
      - "6 注释" / "6、注释" / "6. 注释"（整数编号，不含 3.1 这类多级）
      - "第六章 注释" / "第6章 注释"
    以「编号必须严格递增 +1、从 1 起链」过滤伪命中（如正文里的 "3 个接口"）。
    无编号链时回退 markdown 一级标题（# / ## 中层级最高者）。
    """
    candidates: list[tuple[int, str]] = []
    num_re = _re.compile(r"^(\d{1,2})[\s、.]\s*(\S.*)$")
    chap_re = _re.compile(r"^第([0-9一二三四五六七八九十]{1,3})[章部分]\s*(.*)$")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or len(line) > 60 or line[-1] in "。；，,.;":
            continue
        m = chap_re.match(line)
        if m:
            n = _cn_to_int(m.group(1))
            if n is not None and m.group(2).strip():
                candidates.append((n, m.group(2).strip()))
            continue
        m = num_re.match(line.lstrip("#").strip())
        if m and not m.group(2)[0].isdigit() and m.group(2)[0] != ".":
            candidates.append((int(m.group(1)), m.group(2).strip()))

    # 递增链过滤：从 1 开始，只收编号 == 上一个 + 1 的候选
    chain: list[dict] = []
    expect = 1
    for n, title in candidates:
        if n == expect:
            chain.append({"number": str(n), "title": title})
            expect += 1
    if len(chain) >= 2:
        return chain

    # 回退：markdown 标题（取出现的最高层级）
    md = _re.findall(r"^(#{1,3})\s+(.+?)\s*$", text, _re.M)
    if md:
        top = min(len(h) for h, _ in md)
        return [{"number": str(i + 1), "title": t.strip()}
                for i, (h, t) in enumerate(md) if len(h) == top]
    return []


def _normalize_title(t: str) -> str:
    t = _re.sub(r"^[0-9.、\s]+", "", t)
    return _re.sub(r"[\s（）()【】\[\]:：]+", "", t).lower()


def _anchor_covered(anchor_title: str, existing_titles: set[str]) -> bool:
    a = _normalize_title(anchor_title)
    if not a:
        return True
    for e in existing_titles:
        if a == e or (len(a) >= 2 and (a in e or e in a)):
            return True
    return False


def _collect_tree_titles(sections: list[dict]) -> set[str]:
    titles: set[str] = set()
    def walk(nodes):
        for nd in nodes:
            if isinstance(nd, dict):
                titles.add(_normalize_title(nd.get("title", "")))
                titles.add(_normalize_title(nd.get("id", "")))
                walk(nd.get("children", []))
    walk(sections)
    titles.discard("")
    return titles


def _guard_missing_anchors(sections: list[dict], sample_text: str) -> list[dict]:
    """对照预扫描锚点补回被遗漏的一级章节，返回补回清单（结构完整性守卫）."""
    anchors = scan_top_headings(sample_text)
    if not anchors:
        return []
    existing = _collect_tree_titles(sections)
    added = []
    for a in anchors:
        if _anchor_covered(a["title"], existing):
            continue
        sid = _to_kebab_case(a["title"])
        if sid == "template" or sid in {n.get("id") for n in sections if isinstance(n, dict)}:
            sid = f"section-{a['number']}"
        node = {
            "id": sid, "title": a["title"], "level": 1, "children": [],
            "dependency": {"type": "self_contained",
                           "description": "结构预扫描自动补回（模板注册时被 LLM 遗漏的章节）",
                           "expected_sources": []},
        }
        sections.append(node)
        added.append({"id": sid, "number": a["number"], "title": a["title"]})
    return added
