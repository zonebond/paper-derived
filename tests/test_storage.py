"""存储层单元测试."""

import pytest

from paper_derived.storage import (
    ensure_dirs,
    save_template,
    load_template,
    list_all_templates,
    template_exists,
    make_document_id,
    make_session_dir,
    save_session_json,
    load_session_json,
)
from paper_derived.models.template import Template


class TestTemplateStorage:
    def test_save_and_load(self):
        t = Template(
            id="test-save-load", name="Test",
            extraction_prompt="extract", structure_prompt="struct",
            style_prompt="style", validation_prompt="validate",
        )
        save_template(t)
        loaded = load_template("test-save-load")
        assert loaded is not None
        assert loaded.id == "test-save-load"
        assert loaded.extraction_prompt == "extract"

    def test_not_found(self):
        assert load_template("nonexistent-id-12345") is None

    def test_list_contains(self):
        templates = list_all_templates()
        ids = [t.id for t in templates]
        assert "test-save-load" in ids

    def test_exists(self):
        assert template_exists("test-save-load")
        assert not template_exists("nonexistent-id-99999")

    def test_update_overwrites(self):
        t = Template(id="test-update", name="V1",
                     extraction_prompt="v1 extract")
        save_template(t)

        t2 = Template(id="test-update", name="V2",
                      extraction_prompt="v2 extract")
        save_template(t2)

        loaded = load_template("test-update")
        assert loaded is not None
        assert loaded.name == "V2"
        assert loaded.extraction_prompt == "v2 extract"

    def test_make_document_id(self):
        doc_id = make_document_id()
        assert doc_id.startswith("doc_")
        assert len(doc_id) > 4


class TestSessionStorage:
    def test_make_and_use_session_dir(self, tmp_path):
        session_dir = make_session_dir(base=str(tmp_path))
        assert session_dir.exists()

        save_session_json(session_dir, "test.json", {"key": "value"})
        data = load_session_json(session_dir, "test.json")
        assert data["key"] == "value"

    def test_load_missing_file(self, tmp_path):
        session_dir = make_session_dir(base=str(tmp_path))
        with pytest.raises(FileNotFoundError):
            load_session_json(session_dir, "missing.json")
