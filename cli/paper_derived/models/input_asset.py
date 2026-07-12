"""输入资产数据模型."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Entity:
    """从输入中抽取的关键实体."""
    kind: str           # table | field | api_endpoint | term | rule | ...
    name: str
    description: str = ""
    location: str = ""  # 在 raw_content 中的位置引用

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "name": self.name,
            "description": self.description,
            "location": self.location,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Entity":
        return cls(
            kind=d.get("kind", ""),
            name=d.get("name", ""),
            description=d.get("description", ""),
            location=d.get("location", ""),
        )


@dataclass
class InputAsset:
    """已注册的输入资产.

    register_input 的产出，被 extract 和 generate 消费。
    """

    id: str                              # 唯一标识
    name: str                            # 人类可读名称
    type: str = "plain_text"             # markdown | docx | doc | xlsx | xls | pdf | pptx | csv | json_schema | ddl | plain_text
    raw_content: str = ""                # 原始文本
    summary: str = ""                    # LLM 生成的摘要
    entities: list[Entity] = field(default_factory=list)  # 抽取出的关键实体

    # 元数据
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "raw_content": self.raw_content,
            "summary": self.summary,
            "entities": [e.to_dict() for e in self.entities],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "InputAsset":
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            type=d.get("type", "plain_text"),
            raw_content=d.get("raw_content", ""),
            summary=d.get("summary", ""),
            entities=[Entity.from_dict(e) for e in d.get("entities", [])],
            metadata=d.get("metadata", {}),
        )
