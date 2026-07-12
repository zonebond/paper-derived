"""校验报告数据模型 — preflight() 和 validate() 的输出."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SectionPreflight:
    """单个 Section 的体检结果."""
    section_id: str
    section_title: str = ""
    status: str = "ok"                 # ok | warning | critical
    hint: str = ""                     # 如「未发现错误码相关描述」

    def to_dict(self) -> dict:
        return {
            "section_id": self.section_id,
            "section_title": self.section_title,
            "status": self.status,
            "hint": self.hint,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SectionPreflight":
        return cls(
            section_id=d.get("section_id", ""),
            section_title=d.get("section_title", ""),
            status=d.get("status", "ok"),
            hint=d.get("hint", ""),
        )


@dataclass
class PreflightReport:
    """资料体检报告 — preflight() 的输出."""
    ok: bool = True
    sections: list[SectionPreflight] = field(default_factory=list)
    summary: str = ""                  # 「5/6 Section 资料充足，1 个缺资料」

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "sections": [s.to_dict() for s in self.sections],
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PreflightReport":
        return cls(
            ok=d.get("ok", True),
            sections=[SectionPreflight.from_dict(s) for s in d.get("sections", [])],
            summary=d.get("summary", ""),
        )


@dataclass
class ValidationCheckpoint:
    """单个校验项的结果."""
    checkpoint: str                    # 校验项描述
    status: str = "PASSED"            # PASSED | FAILED | WARNING
    section_id: str = ""              # 关联的 Section (为空则全局)
    reason: str = ""                   # 失败原因
    severity: str = "WARNING"         # CRITICAL | WARNING
    rule_type: str = "fixable"        # fixable (可修复) | input_dependent (资料依赖)

    def to_dict(self) -> dict:
        return {
            "checkpoint": self.checkpoint,
            "status": self.status,
            "section_id": self.section_id,
            "reason": self.reason,
            "severity": self.severity,
            "rule_type": self.rule_type,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ValidationCheckpoint":
        return cls(
            checkpoint=d.get("checkpoint", ""),
            status=d.get("status", "PASSED"),
            section_id=d.get("section_id", ""),
            reason=d.get("reason", ""),
            severity=d.get("severity", "WARNING"),
            rule_type=d.get("rule_type", "fixable"),
        )


@dataclass
class ValidationReport:
    """质检报告 — validate() 的输出."""
    passed: bool = True
    total_checkpoints: int = 0
    passed_count: int = 0
    failed_count: int = 0
    checkpoints: list[ValidationCheckpoint] = field(default_factory=list)
    summary: str = ""                  # 「8/10 校验通过，2 个失败 (1 CRITICAL)」

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "total_checkpoints": self.total_checkpoints,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ValidationReport":
        return cls(
            passed=d.get("passed", True),
            total_checkpoints=d.get("total_checkpoints", 0),
            passed_count=d.get("passed_count", 0),
            failed_count=d.get("failed_count", 0),
            checkpoints=[ValidationCheckpoint.from_dict(c) for c in d.get("checkpoints", [])],
            summary=d.get("summary", ""),
        )
