"""路径工具 — 定位 prompts 目录，兼容开发模式和 PyInstaller 打包模式."""

from __future__ import annotations

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