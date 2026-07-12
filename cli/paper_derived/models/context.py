"""上下文存储模型 — CLI 内部的结构化知识库.

Agent 永远不直接看到 ContextStore 的原始数据。
CLI 通过 assemble_section_context() 按 token 预算自动组装最相关的上下文，
Agent 只看到组装后的 prompt。

设计原则:
  - 重活封装在 CLI 内部
  - 声明式查询: 给定 section_id + budget → 自动组装
  - 热力图降级: entity 放不下时输出 compact 目录而非静默 omit
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ContextEntity:
    """上下文实体 — enrich 后的 Entity / ExtractedItem.

    比原始 Entity 多了 related_sections 和 token_count,
    专为上下文组装优化。
    """

    kind: str                         # field | api_endpoint | table | rule | term | value
    name: str
    description: str = ""
    attributes: dict = field(default_factory=dict)
    source_input_id: str = ""
    source_location: str = ""
    confidence: float = 0.0

    # 上下文组装用
    related_sections: list[str] = field(default_factory=list)
    token_count: int = 0              # description + attributes 的 token 数 (惰性计算)
    raw_fragment_key: str = ""        # → ContextStore.raw_fragments 的 key

    @property
    def key(self) -> str:
        """基础键: kind:name。冲突时由 parse_feed_result 追加 :source_input_id 后缀存储到 entity_index。"""
        return f"{self.kind}:{self.name}"

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "name": self.name,
            "description": self.description,
            "attributes": self.attributes,
            "source_input_id": self.source_input_id,
            "source_location": self.source_location,
            "confidence": self.confidence,
            "related_sections": self.related_sections,
            "token_count": self.token_count,
            "raw_fragment_key": self.raw_fragment_key,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ContextEntity":
        return cls(
            kind=d.get("kind", ""),
            name=d.get("name", ""),
            description=d.get("description", ""),
            attributes=d.get("attributes", {}),
            source_input_id=d.get("source_input_id", ""),
            source_location=d.get("source_location", ""),
            confidence=d.get("confidence", 0.0),
            related_sections=d.get("related_sections", []),
            token_count=d.get("token_count", 0),
            raw_fragment_key=d.get("raw_fragment_key", ""),
        )


@dataclass
class SectionExtraction:
    """Section → entity 映射.

    替代原始 SectionExtract，用 entity_keys 引用 ContextStore.entity_index,
    避免数据重复。
    """

    section_id: str
    section_title: str = ""
    entity_keys: list[str] = field(default_factory=list)  # → ContextStore.entity_index 的 key
    confidence: float = 0.0
    hint: str = ""                     # 数据缺口提示

    def to_dict(self) -> dict:
        return {
            "section_id": self.section_id,
            "section_title": self.section_title,
            "entity_keys": self.entity_keys,
            "confidence": self.confidence,
            "hint": self.hint,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SectionExtraction":
        return cls(
            section_id=d.get("section_id", ""),
            section_title=d.get("section_title", ""),
            entity_keys=d.get("entity_keys", []),
            confidence=d.get("confidence", 0.0),
            hint=d.get("hint", ""),
        )


@dataclass
class SectionSummary:
    """已完成 Section 的压缩摘要.

    生成后自动存入 ContextStore，Agent 不可见。
    用于后续 Section 的跨节上下文 (summary_context_text)。
    """

    section_id: str
    title: str = ""
    summary: str = ""                  # 2-4 句压缩
    key_entities: list[str] = field(default_factory=list)  # 本节涉及的 entity_keys
    token_count: int = 0
    generated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "section_id": self.section_id,
            "title": self.title,
            "summary": self.summary,
            "key_entities": self.key_entities,
            "token_count": self.token_count,
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SectionSummary":
        return cls(
            section_id=d.get("section_id", ""),
            title=d.get("title", ""),
            summary=d.get("summary", ""),
            key_entities=d.get("key_entities", []),
            token_count=d.get("token_count", 0),
            generated_at=d.get("generated_at", ""),
        )


@dataclass
class AssembledContext:
    """context_store.query() 的输出 — 组装好的上下文片段.

    每个 Section 生成时，CLI 从 ContextStore 查询得到此对象,
    然后拼接成 prompt 的 user_message 部分。
    """

    section_id: str

    # 按 prompt 结构分层的上下文
    glossary_text: str = ""            # 始终包含 (可缓存前缀)
    style_guide_text: str = ""         # 始终包含 (可缓存前缀)
    validation_rules_text: str = ""    # 始终包含
    structure_context_text: str = ""   # 本节结构指令
    entity_context_text: str = ""      # 相关实体 + 原文片段
    summary_context_text: str = ""     # 相关已完成 Section 摘要

    # 热力图降级: entity 放不下时输出 compact 目录
    entity_catalog_text: str = ""      # "以下实体因预算被压缩为目录: ..."

    # 预算报告
    total_tokens_used: int = 0
    budget: int = 0
    omitted_entities: list[str] = field(default_factory=list)
    omitted_summaries: list[str] = field(default_factory=list)

    def to_prompt_text(self) -> str:
        """拼装所有上下文为完整的 user_message 字符串."""
        parts = []
        if self.glossary_text:
            parts.append(f"## 术语表\n{self.glossary_text}")
        if self.style_guide_text:
            parts.append(f"## 风格指南\n{self.style_guide_text}")
        if self.validation_rules_text:
            parts.append(f"## 校验规则\n{self.validation_rules_text}")
        if self.structure_context_text:
            parts.append(f"## 结构指令\n{self.structure_context_text}")
        if self.entity_context_text:
            parts.append(f"## 相关实体与资料\n{self.entity_context_text}")
        if self.entity_catalog_text:
            parts.append(self.entity_catalog_text)
        if self.summary_context_text:
            parts.append(f"## 已完成章节摘要（供交叉引用）\n{self.summary_context_text}")
        return "\n\n".join(parts)

    def to_dict(self) -> dict:
        return {
            "section_id": self.section_id,
            "glossary_text": self.glossary_text,
            "style_guide_text": self.style_guide_text,
            "validation_rules_text": self.validation_rules_text,
            "structure_context_text": self.structure_context_text,
            "entity_context_text": self.entity_context_text,
            "summary_context_text": self.summary_context_text,
            "entity_catalog_text": self.entity_catalog_text,
            "total_tokens_used": self.total_tokens_used,
            "budget": self.budget,
            "omitted_entities": self.omitted_entities,
            "omitted_summaries": self.omitted_summaries,
        }


@dataclass
class ContextStore:
    """CLI 内部的结构化知识库.

    Agent 不直接看到此对象。CLI 通过 query() 方法按 token 预算
    自动组装最相关的上下文，返回 AssembledContext。

    数据来源:
      - 模板 → glossary, style_rules, validation_rules
      - ctx:feed → entity_index, extraction_map, raw_fragments
      - Section 生成后 → section_summaries (自动填充)
    """

    # ── 模板来源 (加载一次, 不变, 可缓存) ──
    glossary: dict[str, str] = field(default_factory=dict)         # term → definition
    style_rules: list[str] = field(default_factory=list)
    validation_rules: list[str] = field(default_factory=list)

    # ── 输入资产实体 (ctx:feed 填充) ──
    entity_index: dict[str, ContextEntity] = field(default_factory=dict)
    extraction_map: dict[str, SectionExtraction] = field(default_factory=dict)

    # ── 原文片段 (按 entity 索引, 精准检索) ──
    raw_fragments: dict[str, str] = field(default_factory=dict)    # entity_key → 相关原文

    # ── 已完成 Section 摘要 (生成后自动填充) ──
    section_summaries: dict[str, SectionSummary] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "glossary": self.glossary,
            "style_rules": self.style_rules,
            "validation_rules": self.validation_rules,
            "entity_index": {k: v.to_dict() for k, v in self.entity_index.items()},
            "extraction_map": {k: v.to_dict() for k, v in self.extraction_map.items()},
            "raw_fragments": self.raw_fragments,
            "section_summaries": {k: v.to_dict() for k, v in self.section_summaries.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ContextStore":
        ei_raw = d.get("entity_index", {})
        entity_index = {k: ContextEntity.from_dict(v) for k, v in ei_raw.items()}

        em_raw = d.get("extraction_map", {})
        extraction_map = {k: SectionExtraction.from_dict(v) for k, v in em_raw.items()}

        ss_raw = d.get("section_summaries", {})
        section_summaries = {k: SectionSummary.from_dict(v) for k, v in ss_raw.items()}

        return cls(
            glossary=d.get("glossary", {}),
            style_rules=d.get("style_rules", []),
            validation_rules=d.get("validation_rules", []),
            entity_index=entity_index,
            extraction_map=extraction_map,
            raw_fragments=d.get("raw_fragments", {}),
            section_summaries=section_summaries,
        )
