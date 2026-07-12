"""数据模型单元测试."""

import json

from paper_derived.models.template import Template, TemplateSummary
from paper_derived.models.input_asset import InputAsset, Entity
from paper_derived.models.document import (
    DocumentTree, Section, DocumentMeta, LineageRef,
)
from paper_derived.models.extraction import (
    ExtractionResult, SectionExtract, ExtractedItem,
)
from paper_derived.models.reports import (
    PreflightReport, SectionPreflight,
    ValidationReport, ValidationCheckpoint,
)


class TestTemplate:
    def test_to_from_dict(self):
        t = Template(
            id="my-template",
            name="My Template",
            description="A test template",
            extraction_prompt="Extract fields",
            structure_prompt="Sections: intro, body",
            style_prompt="Concise style",
            validation_prompt="Check completeness",
            section_ids=["intro", "body"],
        )
        d = t.to_dict()
        t2 = Template.from_dict(d)
        assert t2.id == "my-template"
        assert t2.extraction_prompt == "Extract fields"
        assert t2.section_ids == ["intro", "body"]

    def test_summary_to_dict(self):
        s = TemplateSummary(id="t1", name="T1", section_count=3)
        d = s.to_dict()
        assert d["id"] == "t1"
        assert d["section_count"] == 3


class TestInputAsset:
    def test_to_from_dict(self):
        asset = InputAsset(
            id="inp-1", name="需求文档", type="markdown",
            raw_content="# 用户模块\n\n接口: POST /users",
            summary="描述了用户模块和接口",
            entities=[Entity(kind="api_endpoint", name="POST /users",
                             description="创建用户", location="§1")],
            metadata={"source": "./req.md"},
        )
        d = asset.to_dict()
        a2 = InputAsset.from_dict(d)
        assert a2.id == "inp-1"
        assert a2.entities[0].kind == "api_endpoint"
        assert a2.entities[0].name == "POST /users"

    def test_empty_entities(self):
        asset = InputAsset(id="e", name="Empty")
        assert asset.entities == []
        d = asset.to_dict()
        assert d["entities"] == []


class TestDocumentTree:
    def test_to_from_dict(self):
        doc = DocumentTree(
            document_id="doc_abc",
            template_id="api-design",
            title="User API 设计",
            sections=[
                Section(id="overview", title="概述", content="...", status="generated",
                        lineage=[LineageRef(input_id="inp-1", confidence=0.9)]),
                Section(id="error-codes", title="错误码", status="placeholder",
                        hints=["资料不足：未发现错误码定义"]),
            ],
        )
        d = doc.to_dict()
        doc2 = DocumentTree.from_dict(d)
        assert doc2.document_id == "doc_abc"
        assert len(doc2.sections) == 2
        assert doc2.sections[0].status == "generated"
        assert doc2.sections[1].status == "placeholder"
        assert doc2.sections[1].hints == ["资料不足：未发现错误码定义"]

    def test_find_section(self):
        doc = DocumentTree(sections=[
            Section(id="a", title="A", children=[
                Section(id="b", title="B", children=[
                    Section(id="c", title="C"),
                ]),
            ]),
        ])
        assert doc.find_section("a") is not None
        assert doc.find_section("c") is not None
        assert doc.find_section("c").title == "C"
        assert doc.find_section("x") is None

    def test_update_section(self):
        doc = DocumentTree(sections=[
            Section(id="a", title="A", content="old"),
        ])
        found = doc.update_section("a", Section(id="a", title="A", content="new"))
        assert found
        assert doc.sections[0].content == "new"
        assert not doc.update_section("x", Section(id="x", title="X"))

    def test_count_sections(self):
        doc = DocumentTree(sections=[
            Section(id="a", title="A", status="generated", children=[
                Section(id="b", title="B", status="placeholder"),
            ]),
            Section(id="c", title="C", status="generated"),
        ])
        t, g, p = doc.count_sections()
        assert (t, g, p) == (3, 2, 1)

    def test_metadata_roundtrip(self):
        meta = DocumentMeta(
            model="claude-sonnet-4-6",
            total_sections=5,
            generated_sections=4,
            placeholder_sections=1,
            validation_score=0.9,
        )
        d = meta.to_dict()
        m2 = DocumentMeta.from_dict(d)
        assert m2.validation_score == 0.9

    def test_lineage_ref(self):
        lr = LineageRef(input_id="i1", fragment_ref="§2", confidence=0.85)
        d = lr.to_dict()
        lr2 = LineageRef.from_dict(d)
        assert lr2.input_id == "i1"
        assert lr2.confidence == 0.85


class TestExtraction:
    def test_extraction_result(self):
        result = ExtractionResult(
            summary="发现 2 个接口",
            sections=[
                SectionExtract(
                    section_id="endpoints", section_title="接口定义",
                    found=[ExtractedItem(kind="api_endpoint", name="POST /users",
                                         attributes={"method": "POST"}, confidence=0.95)],
                    confidence=0.9,
                ),
            ],
            warnings=["缺少错误码"],
        )
        d = result.to_dict()
        r2 = ExtractionResult.from_dict(d)
        assert r2.summary == "发现 2 个接口"
        assert r2.sections[0].found[0].name == "POST /users"
        assert r2.warnings == ["缺少错误码"]

    def test_extracted_item_empty_attrs(self):
        item = ExtractedItem(kind="field", name="age")
        assert item.attributes == {}
        d = item.to_dict()
        assert d["attributes"] == {}


class TestReports:
    def test_preflight_report(self):
        report = PreflightReport(
            ok=True,
            sections=[
                SectionPreflight(section_id="s1", section_title="概述", status="ok"),
                SectionPreflight(section_id="s2", section_title="错误码",
                                 status="warning", hint="未发现错误码定义"),
            ],
            summary="1/2 资料充足",
        )
        d = report.to_dict()
        r2 = PreflightReport.from_dict(d)
        assert r2.ok is True
        assert r2.sections[1].status == "warning"

    def test_validation_report(self):
        report = ValidationReport(
            passed=False,
            total_checkpoints=4,
            passed_count=3,
            failed_count=1,
            checkpoints=[
                ValidationCheckpoint(
                    checkpoint="所有字段必须有类型",
                    status="FAILED",
                    section_id="endpoints",
                    reason="age 字段缺少类型",
                    severity="CRITICAL",
                    rule_type="fixable",
                ),
            ],
            summary="3/4 通过",
        )
        d = report.to_dict()
        r2 = ValidationReport.from_dict(d)
        assert r2.passed is False
        assert r2.checkpoints[0].severity == "CRITICAL"
        assert r2.checkpoints[0].rule_type == "fixable"
