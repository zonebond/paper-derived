"""Paper Derived — 文档生成引擎。

无状态引擎 CLI。正向注册模板，逆向生成文档。
"""

__version__ = "0.2.0"  # 与 pyproject.toml 的 [project].version 保持一致


def get_version_info() -> dict:
    """完整版本信息：版本号 + 构建期烙进的 commit/时间（无构建信息时为空串）."""
    info = {"version": __version__, "commit": "", "built_at": ""}
    try:
        from paper_derived import _buildinfo  # 由 build-cli.sh 生成，不入库
        info["commit"] = getattr(_buildinfo, "BUILD_COMMIT", "")
        info["built_at"] = getattr(_buildinfo, "BUILD_DATE", "")
    except ImportError:
        pass
    return info
