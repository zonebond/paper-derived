"""Session 持久化 — checkpoint 到磁盘, 支持断点续传.

Session 目录结构:
  .runner/sessions/{session_id}/
  ├── session.json              # GenerationSession
  ├── context_store.json        # ContextStore (独立文件, 体积可能较大)
  ├── document.json             # 当前 DocumentTree 快照
  └── output/                   # 增量 Section 输出
      ├── section-overview.md
      └── ...
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from paper_derived.models.session import GenerationSession, now_iso
from paper_derived.models.context import ContextStore
from paper_derived.models.document import DocumentTree

# 项目级 .runner 目录 (优先) 或全局 ~/.paper-derived/sessions/
def _find_project_root() -> Path | None:
    """从 cwd 向上遍历找项目根（含 .git 或 .runner 的目录）。"""
    current = Path.cwd()
    while True:
        if (current / ".git").exists() or (current / ".runner").exists():
            return current
        parent = current.parent
        if parent == current:
            break  # 到达文件系统根
        current = parent
    return None


def _sessions_root() -> Path:
    """确定 session 存储根目录.

    从 cwd 向上查找项目根（含 .git 或 .runner），
    优先使用项目根下的 .runner/sessions/，
    回退到 ~/.paper-derived/sessions/。
    """
    project_root = _find_project_root()
    if project_root is not None:
        local = project_root / ".runner" / "sessions"
        local.mkdir(parents=True, exist_ok=True)
        return local
    global_dir = Path.home() / ".paper-derived" / "sessions"
    global_dir.mkdir(parents=True, exist_ok=True)
    return global_dir


def session_dir(session_id: str) -> Path:
    """获取 session 目录路径."""
    return _sessions_root() / session_id


def save_session(session: GenerationSession, context_store: ContextStore | None = None) -> Path:
    """保存完整 session 状态到磁盘.

    Args:
        session: GenerationSession 对象
        context_store: 可选的 ContextStore 对象 (独立存储)

    Returns:
        session 目录路径
    """
    d = session_dir(session.session_id)
    d.mkdir(parents=True, exist_ok=True)

    # 主 session 文件
    (d / "session.json").write_text(
        json.dumps(session.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Context Store 独立文件 (体积可能较大)
    if context_store is not None:
        (d / "context_store.json").write_text(
            json.dumps(context_store.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return d


def save_document(session_id: str, document: DocumentTree) -> Path:
    """保存 DocumentTree 快照到 session 目录."""
    d = session_dir(session_id)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "document.json"
    path.write_text(
        json.dumps(document.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_session(session_id: str) -> tuple[GenerationSession, ContextStore, DocumentTree | None]:
    """加载 session 状态.

    Returns:
        (session, context_store, document) — context_store 始终返回非 None（文件缺失时返回空 ContextStore）
    """
    d = session_dir(session_id)
    if not (d / "session.json").exists():
        raise FileNotFoundError(f"Session 不存在: {session_id}")

    # Session
    data = json.loads((d / "session.json").read_text(encoding="utf-8"))
    session = GenerationSession.from_dict(data)

    # Context Store — 始终返回非 None，防止数据丢失
    context_store = ContextStore()
    ctx_path = d / "context_store.json"
    if ctx_path.exists():
        try:
            ctx_data = json.loads(ctx_path.read_text(encoding="utf-8"))
            context_store = ContextStore.from_dict(ctx_data)
        except (json.JSONDecodeError, KeyError):
            # 文件损坏时返回空 store，但不丢失已有 session 数据
            pass

    # Document
    document = None
    doc_path = d / "document.json"
    if doc_path.exists():
        doc_data = json.loads(doc_path.read_text(encoding="utf-8"))
        document = DocumentTree.from_dict(doc_data)

    return session, context_store, document


def checkpoint_session(
    session: GenerationSession,
    context_store: ContextStore | None = None,
    document: DocumentTree | None = None,
) -> None:
    """Checkpoint session: 更新时间戳 + 递增版本号 + 持久化."""
    session.checkpoint_version += 1
    session.last_checkpoint_at = now_iso()
    session.updated_at = session.last_checkpoint_at

    save_session(session, context_store)
    if document is not None:
        save_document(session.session_id, document)


def list_sessions() -> list[dict]:
    """列出所有 session 的摘要信息."""
    root = _sessions_root()
    results = []
    if not root.exists():
        return results
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        sp = d / "session.json"
        if not sp.exists():
            continue
        try:
            data = json.loads(sp.read_text(encoding="utf-8"))
            session = GenerationSession.from_dict(data)
            results.append({
                "session_id": session.session_id,
                "template_id": session.template_id,
                "phase": session.phase,
                "total": session.total_sections,
                "done": session.done_sections,
                "updated_at": session.updated_at,
            })
        except Exception:
            continue
    return results


def delete_session(session_id: str) -> None:
    """删除 session 目录."""
    d = session_dir(session_id)
    if d.exists():
        shutil.rmtree(d)
