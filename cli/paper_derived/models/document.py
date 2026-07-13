"""文档树数据模型 — 引擎核心输出类型."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from uuid import uuid4

_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
_NUM_PREFIX_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)*[.、]?\s*")


def _heading_text(line: str) -> str | None:
    """若该行是 markdown 标题，返回去掉 # 与章节编号后的标题文本；否则 None."""
    m = _HEADING_RE.match(line.strip())
    if not m:
        return None
    return _NUM_PREFIX_RE.sub("", m.group(1)).strip()


def sanitize_section_content(
    content: str, titles: list[str], child_titles: list[str]
) -> str:
    """清除 LLM 塞进 content 的重复标题（父子章节重复输出 bug 的确定性防线）.

    规则：
    1. 正文开始前出现的、与本节标题相同的标题行（含 "1 范围" 这类编号变体）→ 删除该行。
       节标题由渲染器统一输出，content 里不该再有一份。
    2. 与任一**直接子节点**标题相同的标题行 → 从该行起截断全部剩余内容。
       子章节由系统单独生成，其后的内容必然是子树的重复。
    """
    if not content:
        return content
    title_set = {t.strip() for t in titles if t and t.strip()}
    child_set = {t.strip() for t in child_titles if t and t.strip()}

    out: list[str] = []
    body_started = False
    for line in content.splitlines():
        heading = _heading_text(line)
        if heading is not None:
            if heading in child_set:
                break
            if heading in title_set and not body_started:
                continue
        if line.strip():
            body_started = True
        out.append(line)
    return "\n".join(out).strip()


@dataclass
class LineageRef:
    """内容来源引用."""
    input_id: str         # 输入资产 ID
    fragment_ref: str = ""  # 资产内的片段引用
    confidence: float = 0.0  # 0~1

    def to_dict(self) -> dict:
        return {
            "input_id": self.input_id,
            "fragment_ref": self.fragment_ref,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LineageRef":
        return cls(
            input_id=d.get("input_id", ""),
            fragment_ref=d.get("fragment_ref", ""),
            confidence=d.get("confidence", 0.0),
        )


@dataclass
class Section:
    """文档 Section 节点.

    可递归嵌套，支持 generated / placeholder / empty 三种状态。
    """

    id: str                              # 全局唯一，模板定义的锚点 ID
    title: str                           # Section 标题
    content: str = ""                    # 正文内容 (Markdown)
    children: list["Section"] = field(default_factory=list)
    level: int = 1                       # 层级深度
    template_ref: str = ""              # 对应模板结构指令中的 Section 定义
    status: str = "empty"               # generated | placeholder | empty
    lineage: list[LineageRef] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)  # 生成时的提示

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "children": [c.to_dict() for c in self.children],
            "level": self.level,
            "template_ref": self.template_ref,
            "status": self.status,
            "lineage": [l.to_dict() for l in self.lineage],
            "hints": self.hints,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Section":
        return cls(
            id=d.get("id", ""),
            title=d.get("title", ""),
            content=d.get("content", ""),
            children=[cls.from_dict(c) for c in d.get("children", [])],
            level=d.get("level", 1),
            template_ref=d.get("template_ref", ""),
            status=d.get("status", "empty"),
            lineage=[LineageRef.from_dict(l) for l in d.get("lineage", [])],
            hints=d.get("hints", []),
        )


@dataclass
class DocumentMeta:
    """文档级元数据."""
    model: str = ""                    # 生成所用的模型
    total_sections: int = 0
    generated_sections: int = 0
    placeholder_sections: int = 0
    validation_score: float | None = None
    custom: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "total_sections": self.total_sections,
            "generated_sections": self.generated_sections,
            "placeholder_sections": self.placeholder_sections,
            "validation_score": self.validation_score,
            "custom": self.custom,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DocumentMeta":
        return cls(
            model=d.get("model", ""),
            total_sections=d.get("total_sections", 0),
            generated_sections=d.get("generated_sections", 0),
            placeholder_sections=d.get("placeholder_sections", 0),
            validation_score=d.get("validation_score"),
            custom=d.get("custom", {}),
        )


@dataclass
class DocumentTree:
    """文档树 — 引擎核心输出.

    纯内容结构，不含会话状态。平台无关，Section 可精确寻址。
    """

    document_id: str = ""
    template_id: str = ""
    input_ids: list[str] = field(default_factory=list)
    title: str = ""
    generated_at: str = ""
    sections: list[Section] = field(default_factory=list)
    metadata: DocumentMeta = field(default_factory=DocumentMeta)

    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "template_id": self.template_id,
            "input_ids": self.input_ids,
            "title": self.title,
            "generated_at": self.generated_at,
            "sections": [s.to_dict() for s in self.sections],
            "metadata": self.metadata.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DocumentTree":
        return cls(
            document_id=d.get("document_id", ""),
            template_id=d.get("template_id", ""),
            input_ids=d.get("input_ids", []),
            title=d.get("title", ""),
            generated_at=d.get("generated_at", ""),
            sections=[Section.from_dict(s) for s in d.get("sections", [])],
            metadata=DocumentMeta.from_dict(d.get("metadata", {})),
        )

    def count_sections(self) -> tuple[int, int, int]:
        """统计 (总, generated, placeholder) 的 Section 数."""
        def walk(sec: Section) -> tuple[int, int, int]:
            t, g, p = 1, int(sec.status == "generated"), int(sec.status == "placeholder")
            for c in sec.children:
                ct, cg, cp = walk(c)
                t += ct; g += cg; p += cp
            return t, g, p
        total, gen, ph = 0, 0, 0
        for s in self.sections:
            st, sg, sp = walk(s)
            total += st; gen += sg; ph += sp
        return total, gen, ph

    def find_section(self, section_id: str) -> Section | None:
        """按 ID 查找 Section."""
        def walk(secs: list[Section]) -> Section | None:
            for s in secs:
                if s.id == section_id:
                    return s
                found = walk(s.children)
                if found:
                    return found
            return None
        return walk(self.sections)

    @classmethod
    def from_template(cls, template_id: str) -> "DocumentTree":
        """从模板构建骨架文档树，无需 LLM.

        所有 section 初始化为 status="empty"，无 content.
        """
        from paper_derived.storage import load_template
        template = load_template(template_id)
        if template is None:
            raise ValueError(f"模板不存在: {template_id}")

        sections = _build_skeleton(
            template.section_ids, template.section_dependencies, template.section_tree,
        )
        return cls(
            document_id=_make_document_id(),
            template_id=template_id,
            title=template.name,
            sections=sections,
        )

    def merge_batch(self, partial: "DocumentTree") -> int:
        """合并分批生成的结果，返回更新的 section 数量.

        遍历 partial 中所有 status != "empty" 的 section，
        按 id 替换到当前文档树中。
        """
        from copy import deepcopy
        count = 0

        def walk(src: list[Section], target: list[Section]) -> int:
            c = 0
            pdict = {s.id: s for s in src}
            for i, t in enumerate(target):
                if t.id in pdict:
                    incoming = pdict[t.id]
                    if incoming.status != "empty":
                        # 保留原有 children（分批生成的 Section 不含子节点）
                        existing_children = t.children
                        target[i] = deepcopy(incoming)
                        target[i].children = existing_children
                        c += 1
                c += walk(src, t.children)
            return c

        count += walk(partial.sections, self.sections)
        self.metadata.generated_sections, self.metadata.placeholder_sections = \
            self.count_sections()[1:3]
        return count

    def collect_section_ids(self) -> list[str]:
        """展平所有 section ID（含子节点）."""
        result = []

        def walk(secs: list[Section]) -> None:
            for s in secs:
                result.append(s.id)
                walk(s.children)

        walk(self.sections)
        return result

    def collect_section_ids_with_levels(self) -> list[tuple[str, int]]:
        """展平所有 section ID 及其层级（含子节点）.

        Returns:
            [(section_id, level), ...] — 用于上下文组装中的结构展示。
        """
        result = []

        def walk(secs: list[Section], depth: int = 1) -> None:
            for s in secs:
                result.append((s.id, depth))
                walk(s.children, depth + 1)

        walk(self.sections)
        return result

    def sanitize_headings(self) -> None:
        """递归清除各节点 content 中重复的自身/子节点标题（见 sanitize_section_content）."""
        def walk(secs: list[Section]) -> None:
            for sec in secs:
                sec.content = sanitize_section_content(
                    sec.content, [sec.title], [c.title for c in sec.children]
                )
                walk(sec.children)
        walk(self.sections)

    def update_section(self, section_id: str, new_section: Section) -> bool:
        """更新指定 ID 的 Section 内容，保留原有子节点，返回是否找到.

        LLM 生成的 Section 只包含 content/status/lineage/hints，
        不包含 children（子节点由模板骨架维护）。
        因此更新时只替换内容字段，保留原有 children。
        """
        def walk(secs: list[Section]) -> bool:
            for i, s in enumerate(secs):
                if s.id == section_id:
                    # 保留原有 children（LLM 不会生成子节点）
                    existing_children = s.children
                    secs[i] = new_section
                    secs[i].children = existing_children
                    return True
                if walk(s.children):
                    return True
            return False
        return walk(self.sections)


# ── Helpers ──────────────────────────────────────────────────────


def _make_document_id() -> str:
    """生成文档唯一 ID."""
    return f"doc_{uuid4().hex[:12]}"


def _build_skeleton(
    section_ids: list[str], section_deps: dict,
    section_tree: list[dict] | None = None,
) -> list[Section]:
    """从模板元数据构建 Section 骨架。

    优先使用 section_tree（带层级），回退到扁平 section_ids。
    """
    if section_tree:
        return _walk_tree(section_tree, section_deps)

    # 扁平回退
    result = []
    for sid in section_ids:
        s = Section(
            id=sid,
            title=sid.replace("-", " ").title(),
            content="",
            level=1,
            status="empty",
        )
        result.append(s)
    return result


def _walk_tree(
    nodes: list[dict], section_deps: dict, level: int = 1,
) -> list[Section]:
    """递归构建 Section 树."""
    result = []
    for node in nodes:
        sid = node.get("id", "")
        s = Section(
            id=sid,
            title=node.get("title", sid.replace("-", " ").title()),
            content="",
            level=node.get("level", level),
            status="empty",
        )
        s.children = _walk_tree(node.get("children", []), section_deps, level + 1)
        result.append(s)
    return result
