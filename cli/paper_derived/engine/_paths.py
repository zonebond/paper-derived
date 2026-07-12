"""路径工具 — 定位 prompts 目录 + prompt 加载（含 compact 变体），兼容开发/打包模式."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def get_prompts_dir() -> Path:
    """定位 prompts 目录.

    开发模式下使用 __file__ 相对路径；
    PyInstaller 打包模式下使用 sys._MEIPASS。
    """
    if getattr(sys, "frozen", False):
        # PyInstaller 打包模式
        return Path(sys._MEIPASS) / "paper_derived" / "prompts"
    # 开发模式
    return Path(__file__).parent.parent / "prompts"


PROMPTS_DIR = get_prompts_dir()

# ── Prompt 加载（compact 变体支持）───────────────────────────────
#
# compact 模式面向小模型/小窗口 Provider：同名精简版 prompt 放在
# prompts/compact/ 下，输出 JSON 契约与标准版完全一致，仅剔除解释性
# 文字。开启方式：
#   - 环境变量 PAPER_DERIVED_COMPACT=1（对所有构造 prompt 的命令生效）
#   - 或代码内 set_compact(True)（session run --compact 用）

_COMPACT_ENV = "PAPER_DERIVED_COMPACT"
_compact_override: bool | None = None


def set_compact(enabled: bool) -> None:
    global _compact_override
    _compact_override = enabled


def compact_enabled() -> bool:
    if _compact_override is not None:
        return _compact_override
    return os.environ.get(_COMPACT_ENV, "").strip().lower() in ("1", "true", "yes", "compact")


def read_prompt(name: str) -> str:
    """读取内置 prompt；compact 模式下优先取 compact 变体，缺失则回退标准版。"""
    if compact_enabled():
        compact_path = PROMPTS_DIR / "compact" / name
        if compact_path.is_file():
            return compact_path.read_text(encoding="utf-8")
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")
