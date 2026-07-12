"""引擎 prompt 构造和解析单元测试."""

import json

from paper_derived.llm import extract_json
from paper_derived.models.document import DocumentTree
from paper_derived.models.input_asset import InputAsset


class TestLLMUtils:
    def test_extract_json_direct(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_extract_json_code_block(self):
        text = '```json\n{"b": 2}\n```'
        assert extract_json(text) == {"b": 2}

    def test_extract_json_embedded(self):
        text = 'some text {"c": 3} more text'
        assert extract_json(text) == {"c": 3}

    def test_extract_json_array(self):
        text = '[{"d": 4}]'
        assert extract_json(text) == [{"d": 4}]


class TestTemplateEngine:
    def test_build_register_prompt(self):
        from paper_derived.engine.template import build_register_template_prompt
        sys_p, user_p = build_register_template_prompt(
            "# API 设计文档\n\n## 概述\n...", "api-design"
        )
        assert len(sys_p) > 100
        assert "API 设计文档" in user_p
        assert "# API 设计文档" not in sys_p  # system prompt is template, not sample

    def test_build_register_prompt_returns_strings(self):
        from paper_derived.engine.template import build_register_template_prompt
        sys_p, user_p = build_register_template_prompt("sample", "test")
        assert isinstance(sys_p, str)
        assert isinstance(user_p, str)

    def test_list_all(self):
        from paper_derived.engine.template import list_all
        result = list_all()
        assert isinstance(result, list)

    def test_get_template_nonexistent(self):
        from paper_derived.engine.template import get_template
        assert get_template("nonexistent-12345-xyz") is None


class TestInputEngine:
    def test_build_register_input_prompt(self):
        from paper_derived.engine.input_asset import build_register_input_prompt
        sys_p, user_p = build_register_input_prompt("POST /users ...", "需求文档")
        assert len(sys_p) > 50
        assert "POST /users" in user_p


class TestGeneratorEngine:
    def test_build_preflight_prompt(self):
        from paper_derived.engine.generator import build_preflight_prompt
        asset = InputAsset(id="a", name="需求", raw_content="some content")
        sys_p, user_p = build_preflight_prompt([asset], "test-api")
        assert len(sys_p) > 50
        assert "some content" in user_p

    def test_build_extract_prompt(self):
        from paper_derived.engine.generator import build_extract_prompt
        asset = InputAsset(id="a", name="需求", raw_content="fields: name, age")
        sys_p, user_p = build_extract_prompt([asset], "test-api")
        assert len(sys_p) > 50

    def test_build_generate_prompt(self):
        from paper_derived.engine.generator import build_generate_prompt
        asset = InputAsset(id="a", name="需求", raw_content="content")
        sys_p, user_p = build_generate_prompt([asset], "test-api")
        assert len(sys_p) > 50

    def test_build_generate_prompt_with_overrides(self):
        from paper_derived.engine.generator import build_generate_prompt
        asset = InputAsset(id="a", name="需求", raw_content="content")
        overrides = {"summary": "corrected"}
        sys_p, user_p = build_generate_prompt([asset], "test-api", overrides)
        assert "corrected" in user_p


class TestValidatorEngine:
    def test_build_validate_prompt(self):
        from paper_derived.engine.validator import build_validate_prompt
        doc = DocumentTree(
            document_id="d1", template_id="test-api", title="Test",
        )
        sys_p, user_p = build_validate_prompt(doc, "test-api")
        assert len(sys_p) > 50


class TestDocOpsEngine:
    def test_build_revise_section_prompt(self):
        from paper_derived.engine.doc_ops import build_revise_section_prompt
        from paper_derived.models.document import Section
        doc = DocumentTree(sections=[
            Section(id="s1", title="Intro", content="hello")
        ])
        sys_p, user_p = build_revise_section_prompt(doc, "s1", "make it formal")
        assert "s1" in user_p
        assert "make it formal" in user_p

    def test_build_revise_global_prompt(self):
        from paper_derived.engine.doc_ops import build_revise_global_prompt
        doc = DocumentTree(title="Test Doc")
        sys_p, user_p = build_revise_global_prompt(doc, "use formal tone")
        assert "formal tone" in user_p


class TestPromptConstruction:
    """确保所有 build_xxx_prompt 返回 2-tuple of str."""
    def test_all_build_functions_return_tuple_of_str(self):
        from paper_derived.engine.template import build_register_template_prompt
        from paper_derived.engine.input_asset import build_register_input_prompt
        from paper_derived.engine.generator import (
            build_preflight_prompt, build_extract_prompt, build_generate_prompt,
        )
        from paper_derived.engine.doc_ops import (
            build_revise_section_prompt, build_revise_global_prompt,
        )
        asset = InputAsset(id="a", name="x", raw_content="content")

        for fn, args in [
            (build_register_template_prompt, ("sample", "test")),
            (build_register_input_prompt, ("text", "name")),
            (build_preflight_prompt, ([asset], "test-api")),
            (build_extract_prompt, ([asset], "test-api")),
            (build_generate_prompt, ([asset], "test-api")),
            (build_revise_section_prompt, (DocumentTree(title="T"), "s1", "fix")),
            (build_revise_global_prompt, (DocumentTree(title="T"), "fix")),
        ]:
            sys_p, user_p = fn(*args)
            assert isinstance(sys_p, str), f"{fn.__name__} system is not str"
            assert isinstance(user_p, str), f"{fn.__name__} user is not str"
            assert len(sys_p) > 0
            assert len(user_p) > 0


class TestPromptsDir:
    """测试 PROMPTS_DIR 在开发模式下正确定位。"""

    def test_prompts_dir_exists(self):
        from paper_derived.engine._paths import PROMPTS_DIR
        assert PROMPTS_DIR.exists(), f"PROMPTS_DIR 不存在: {PROMPTS_DIR}"

    def test_prompts_dir_has_seven_files(self):
        from paper_derived.engine._paths import PROMPTS_DIR
        md_files = list(PROMPTS_DIR.glob("*.md"))
        assert len(md_files) == 7, f"期望 7 个 .md 文件，找到 {len(md_files)}: {md_files}"
