"""中间产物抽取结果 — extract() 的输出."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExtractedItem:
    """单个抽取实体."""
    kind: str                                    # field | api_endpoint | table | rule | term | value
    name: str
    attributes: dict = field(default_factory=dict)  # {type: "string", required: "true", ...}
    source_input_id: str = ""
    source_location: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "name": self.name,
            "attributes": self.attributes,
            "source_input_id": self.source_input_id,
            "source_location": self.source_location,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ExtractedItem":
        return cls(
            kind=d.get("kind", ""),
            name=d.get("name", ""),
            attributes=d.get("attributes", {}),
            source_input_id=d.get("source_input_id", ""),
            source_location=d.get("source_location", ""),
            confidence=d.get("confidence", 0.0),
        )


@dataclass
class SectionExtract:
    """按模板 Section 分组的抽取结果."""
    section_id: str
    section_title: str = ""
    found: list[ExtractedItem] = field(default_factory=list)
    confidence: float = 0.0
    hint: str = ""                               # 资料不足提示

    def to_dict(self) -> dict:
        return {
            "section_id": self.section_id,
            "section_title": self.section_title,
            "found": [f.to_dict() for f in self.found],
            "confidence": self.confidence,
            "hint": self.hint,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SectionExtract":
        return cls(
            section_id=d.get("section_id", ""),
            section_title=d.get("section_title", ""),
            found=[ExtractedItem.from_dict(f) for f in d.get("found", [])],
            confidence=d.get("confidence", 0.0),
            hint=d.get("hint", ""),
        )


@dataclass
class ExtractionResult:
    """抽取结果 — extract() 的完整输出.

    第二段交互「轻量预览」的数据源。
    """

    summary: str = ""                            # 人类可读的抽取摘要
    sections: list[SectionExtract] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "sections": [s.to_dict() for s in self.sections],
            "warnings": self.warnings,
        }

    def get_entities_for_section(self, section_id: str) -> list[ExtractedItem]:
        """获取指定 Section 关联的实体列表."""
        for sec in self.sections:
            if sec.section_id == section_id:
                return sec.found
        return []

    @classmethod
    def from_dict(cls, d: dict) -> "ExtractionResult":
        return cls(
            summary=d.get("summary", ""),
            sections=[SectionExtract.from_dict(s) for s in d.get("sections", [])],
            warnings=d.get("warnings", []),
        )
