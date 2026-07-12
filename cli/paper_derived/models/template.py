"""模板数据模型 — 四模块复合模板 Prompt."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Template:
    """四模块复合模板。

    注册模板时从样例文档自动生成四个子模块的 prompt。
    """

    id: str                                    # 模板唯一标识 (kebab-case)
    name: str                                  # 人类可读名称
    description: str = ""                      # 描述
    version: int = 1                           # 版本号 (git 管理)

    # 四模块 prompt
    extraction_prompt: str = ""                # 抽取指令：「每个 Section 对应什么输入特征」
    structure_prompt: str = ""                 # 结构指令：「文档骨架、必须的 Section」
    style_prompt: str = ""                     # 风格指令：「术语库、语气、句式」
    validation_prompt: str = ""                # 校验指令：「Checklist、硬性指标」

    # Placeholder sections (从结构指令中解析出的 Section ID 列表)
    section_ids: list[str] = field(default_factory=list)

    # 每个 Section 的依赖类型: section_id -> { "type": "input_dependent" | "self_contained", "sources": [...] }
    section_dependencies: dict = field(default_factory=dict)

    # Section 树结构: [{ "id": ..., "title": ..., "level": 1, "children": [...] }]
    # 用于从模板重建带层级的文档骨架
    section_tree: list[dict] = field(default_factory=list)

    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "extraction_prompt": self.extraction_prompt,
            "structure_prompt": self.structure_prompt,
            "style_prompt": self.style_prompt,
            "validation_prompt": self.validation_prompt,
            "section_ids": self.section_ids,
            "section_dependencies": self.section_dependencies,
            "section_tree": self.section_tree,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Template":
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            description=d.get("description", ""),
            version=d.get("version", 1),
            extraction_prompt=d.get("extraction_prompt", ""),
            structure_prompt=d.get("structure_prompt", ""),
            style_prompt=d.get("style_prompt", ""),
            validation_prompt=d.get("validation_prompt", ""),
            section_ids=d.get("section_ids", []),
            section_dependencies=d.get("section_dependencies", {}),
            section_tree=d.get("section_tree", []),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )


@dataclass
class TemplateSummary:
    """模板列表项摘要."""
    id: str
    name: str
    description: str = ""
    version: int = 1
    section_count: int = 0
    section_ids: list[str] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "section_count": self.section_count,
            "section_ids": self.section_ids,
            "created_at": self.created_at,
        }
