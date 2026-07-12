"""生成会话数据模型 — Session-Driven Iterative Generation 的核心状态.

Session 是断点续传的单元：每次 checkpoint 持久化到磁盘，
中断后可从上次 checkpoint 恢复，跳过已完成的 Section。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class SectionProgress:
    """单个 Section 的生成进度追踪."""

    section_id: str
    status: str = "pending"          # pending | ready | generating | done | failed
    depends_on: list[str] = field(default_factory=list)
    attempt_count: int = 0
    last_attempt_at: str = ""

    def to_dict(self) -> dict:
        return {
            "section_id": self.section_id,
            "status": self.status,
            "depends_on": self.depends_on,
            "attempt_count": self.attempt_count,
            "last_attempt_at": self.last_attempt_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SectionProgress":
        return cls(
            section_id=d.get("section_id", ""),
            status=d.get("status", "pending"),
            depends_on=d.get("depends_on", []),
            attempt_count=d.get("attempt_count", 0),
            last_attempt_at=d.get("last_attempt_at", ""),
        )


@dataclass
class GenerationSession:
    """文档生成会话 — 可断点续传的工作单元.

    生命周期:
        init → feeding → generating → assembling → complete

    持久化:
        ~/.paper-derived/sessions/{session_id}/session.json
        (或 .runner/sessions/{session_id}/session.json)
    """

    session_id: str
    template_id: str
    created_at: str = ""
    updated_at: str = ""
    phase: str = "init"              # init | feeding | generating | assembling | auditing | complete

    # 已注册的输入资产 ID 列表
    input_asset_ids: list[str] = field(default_factory=list)

    # Section 生成进度
    section_progress: dict[str, SectionProgress] = field(default_factory=dict)

    # Token 预算 (per-section prompt)
    token_budget: int = 120_000

    # 输出配置
    output_path: str = ""            # 最终输出文件路径
    output_format: str = ""          # md | docx | pdf | json

    # Checkpoint 元数据
    checkpoint_version: int = 0
    last_checkpoint_at: str = ""

    # ── 统计 ──

    @property
    def total_sections(self) -> int:
        return len(self.section_progress)

    @property
    def done_sections(self) -> int:
        return sum(1 for sp in self.section_progress.values() if sp.status == "done")

    @property
    def ready_sections(self) -> list[str]:
        """依赖已满足、可以立即生成的 Section ID 列表."""
        result = []
        for sid, sp in self.section_progress.items():
            if sp.status not in ("pending", "ready"):
                continue
            deps_met = all(
                self.section_progress.get(dep, SectionProgress(section_id=dep)).status == "done"
                for dep in sp.depends_on
            )
            if deps_met:
                result.append(sid)
        return result

    @property
    def all_done(self) -> bool:
        return all(
            sp.status in ("done", "placeholder", "skipped")
            for sp in self.section_progress.values()
        )

    # ── 序列化 ──

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "template_id": self.template_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "phase": self.phase,
            "input_asset_ids": self.input_asset_ids,
            "section_progress": {sid: sp.to_dict() for sid, sp in self.section_progress.items()},
            "token_budget": self.token_budget,
            "output_path": self.output_path,
            "output_format": self.output_format,
            "checkpoint_version": self.checkpoint_version,
            "last_checkpoint_at": self.last_checkpoint_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GenerationSession":
        sp_raw = d.get("section_progress", {})
        section_progress = {
            sid: SectionProgress.from_dict(sp) for sid, sp in sp_raw.items()
        }
        return cls(
            session_id=d.get("session_id", ""),
            template_id=d.get("template_id", ""),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            phase=d.get("phase", "init"),
            input_asset_ids=d.get("input_asset_ids", []),
            section_progress=section_progress,
            token_budget=d.get("token_budget", 120_000),
            output_path=d.get("output_path", ""),
            output_format=d.get("output_format", ""),
            checkpoint_version=d.get("checkpoint_version", 0),
            last_checkpoint_at=d.get("last_checkpoint_at", ""),
        )


def make_session_id() -> str:
    """生成会话唯一 ID."""
    from uuid import uuid4
    return f"sess_{uuid4().hex[:12]}"


def now_iso() -> str:
    """当前 UTC 时间的 ISO 格式字符串."""
    return datetime.now(timezone.utc).isoformat()
