"""本地文件存储层.

模板存储: ~/.paper-derived/templates/{id}/profile.json
索引存储: ~/.paper-derived/templates/index.json
会话存储: sessions/{session_id}/ (按需)
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from paper_derived.models.template import Template, TemplateSummary

TEMPLATES_DIR = Path.home() / ".paper-derived" / "templates"
INDEX_FILE = TEMPLATES_DIR / "index.json"


def ensure_dirs() -> None:
    """确保存储目录存在."""
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


def _load_index() -> list[dict]:
    """加载模板索引."""
    ensure_dirs()
    if INDEX_FILE.exists():
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    return []


def _save_index(index: list[dict]) -> None:
    """保存模板索引."""
    ensure_dirs()
    INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def save_template(template: Template) -> Path:
    """保存模板到存储目录.

    返回模板目录路径。
    """
    ensure_dirs()
    template_dir = TEMPLATES_DIR / template.id
    template_dir.mkdir(parents=True, exist_ok=True)

    profile_path = template_dir / "profile.json"
    profile_path.write_text(
        json.dumps(template.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 更新索引
    index = _load_index()
    existing = [i for i, entry in enumerate(index) if entry.get("id") == template.id]
    entry = {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "version": template.version,
        "section_count": len(template.section_ids),
        "section_ids": template.section_ids,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }
    if existing:
        index[existing[0]] = entry
    else:
        index.append(entry)
    _save_index(index)

    return template_dir


def load_template(template_id: str) -> Template | None:
    """从存储加载模板."""
    ensure_dirs()
    profile_path = TEMPLATES_DIR / template_id / "profile.json"
    if not profile_path.exists():
        return None
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    return Template.from_dict(data)


def list_all_templates() -> list[TemplateSummary]:
    """列出所有模板摘要.

    优先从索引读取 section_ids；如果索引中没有（旧版数据），
    则从 profile.json 加载以补充。
    """
    ensure_dirs()
    index = _load_index()
    results = []
    for e in index:
        section_ids = e.get("section_ids", [])
        # 旧版索引可能没有 section_ids，从 profile.json 补充
        if not section_ids:
            tpl = load_template(e.get("id", ""))
            if tpl:
                section_ids = tpl.section_ids
        results.append(TemplateSummary(
            id=e.get("id", ""),
            name=e.get("name", ""),
            description=e.get("description", ""),
            version=e.get("version", 1),
            section_count=e.get("section_count", 0),
            section_ids=section_ids,
            created_at=e.get("created_at", ""),
        ))
    return results


def template_exists(template_id: str) -> bool:
    """检查模板是否存在."""
    return (TEMPLATES_DIR / template_id / "profile.json").exists()


def find_template_by_name(name: str) -> Template | None:
    """按名称查找模板（精确匹配 name 字段）.

    返回第一个名称完全匹配的模板，未找到返回 None。
    """
    ensure_dirs()
    index = _load_index()
    for entry in index:
        if entry.get("name") == name:
            return load_template(entry["id"])
    return None


def delete_template(template_id: str) -> None:
    """删除模板（目录 + 索引条目）."""
    import shutil

    template_dir = TEMPLATES_DIR / template_id
    if template_dir.exists():
        shutil.rmtree(template_dir)

    index = _load_index()
    index = [e for e in index if e.get("id") != template_id]
    _save_index(index)


def make_document_id() -> str:
    """生成文档唯一 ID."""
    return f"doc_{uuid.uuid4().hex[:12]}"


def make_session_dir(base: str | None = None) -> Path:
    """创建会话目录."""
    session_id = f"session_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    if base:
        p = Path(base) / session_id
    else:
        p = Path.cwd() / "sessions" / session_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_session_json(session_dir: Path, filename: str, data: dict) -> Path:
    """在会话目录中保存 JSON 文件."""
    p = session_dir / filename
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load_session_json(session_dir: Path, filename: str) -> dict:
    """从会话目录加载 JSON 文件."""
    p = session_dir / filename
    if not p.exists():
        raise FileNotFoundError(f"会话文件不存在: {p}")
    return json.loads(p.read_text(encoding="utf-8"))
