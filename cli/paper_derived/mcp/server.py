"""MCP Server — 将 paper-derived 引擎能力暴露为 MCP tools.

引擎不调 LLM。MCP tools 提供两种操作:
- build: 构造 prompt 返回给 Agent
- parse: 解析 Agent 的 LLM 响应
"""

from __future__ import annotations

import json

from paper_derived.models.document import DocumentTree
from paper_derived.models.input_asset import InputAsset

TOOLS = [
    # ── Template ──
    {
        "name": "template_register_build",
        "description": "构造模板注册 prompt。返回 system + user prompt，Agent 用自己的 LLM 执行后，用 template_register_parse 解析结果。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sample_text": {"type": "string", "description": "样例文档全文"},
                "name": {"type": "string", "description": "模板名称"},
                "description": {"type": "string", "description": "模板描述"},
            },
            "required": ["sample_text", "name"],
        },
    },
    {
        "name": "template_register_parse",
        "description": "解析模板注册的 LLM 响应，保存并返回 Template 对象。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "llm_response": {"type": "string", "description": "LLM 响应全文"},
                "name": {"type": "string", "description": "模板名称"},
                "description": {"type": "string", "description": "模板描述"},
            },
            "required": ["llm_response", "name"],
        },
    },
    {
        "name": "template_list",
        "description": "列出所有已注册模板。不需要 LLM。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "template_show",
        "description": "查看模板详情。不需要 LLM。",
        "inputSchema": {
            "type": "object",
            "properties": {"template_id": {"type": "string"}},
            "required": ["template_id"],
        },
    },
    # ── Input ──
    {
        "name": "input_register_build",
        "description": "构造输入资产注册 prompt。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "raw_text": {"type": "string", "description": "原始文本"},
                "name": {"type": "string", "description": "资产名称"},
            },
            "required": ["raw_text", "name"],
        },
    },
    {
        "name": "input_register_parse",
        "description": "解析输入资产注册的 LLM 响应。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "llm_response": {"type": "string"},
                "raw_text": {"type": "string"},
                "name": {"type": "string"},
                "source": {"type": "string", "default": ""},
            },
            "required": ["llm_response", "raw_text", "name"],
        },
    },
    # ── Preflight ──
    {
        "name": "gen_preflight_build",
        "description": "构造资料体检 prompt。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_assets": {"type": "array", "items": {"type": "object"}},
                "template_id": {"type": "string"},
            },
            "required": ["input_assets", "template_id"],
        },
    },
    {
        "name": "gen_preflight_parse",
        "description": "解析资料体检的 LLM 响应。",
        "inputSchema": {
            "type": "object",
            "properties": {"llm_response": {"type": "string"}},
            "required": ["llm_response"],
        },
    },
    # ── Extract ──
    {
        "name": "gen_extract_build",
        "description": "构造实体抽取 prompt。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_assets": {"type": "array", "items": {"type": "object"}},
                "template_id": {"type": "string"},
            },
            "required": ["input_assets", "template_id"],
        },
    },
    {
        "name": "gen_extract_parse",
        "description": "解析实体抽取的 LLM 响应。",
        "inputSchema": {
            "type": "object",
            "properties": {"llm_response": {"type": "string"}},
            "required": ["llm_response"],
        },
    },
    # ── Generate ──
    {
        "name": "gen_generate_build",
        "description": "构造文档生成 prompt。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_assets": {"type": "array", "items": {"type": "object"}},
                "template_id": {"type": "string"},
                "extraction_overrides": {"type": "object", "description": "用户修正的抽取结果 (可选)"},
            },
            "required": ["input_assets", "template_id"],
        },
    },
    {
        "name": "gen_generate_parse",
        "description": "解析文档生成的 LLM 响应，返回 DocumentTree。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "llm_response": {"type": "string"},
                "template_id": {"type": "string"},
                "input_assets": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["llm_response", "template_id", "input_assets"],
        },
    },
    # ── Validate ──
    {
        "name": "gen_validate_build",
        "description": "构造质检 prompt。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc": {"type": "object", "description": "DocumentTree JSON"},
                "template_id": {"type": "string"},
            },
            "required": ["doc", "template_id"],
        },
    },
    {
        "name": "gen_validate_parse",
        "description": "解析质检的 LLM 响应。",
        "inputSchema": {
            "type": "object",
            "properties": {"llm_response": {"type": "string"}},
            "required": ["llm_response"],
        },
    },
    # ── Revise ──
    {
        "name": "revise_section_build",
        "description": "构造局部修改 prompt。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc": {"type": "object", "description": "DocumentTree JSON"},
                "section_id": {"type": "string"},
                "instruction": {"type": "string"},
            },
            "required": ["doc", "section_id", "instruction"],
        },
    },
    {
        "name": "revise_global_build",
        "description": "构造全局改写 prompt。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc": {"type": "object", "description": "DocumentTree JSON"},
                "instruction": {"type": "string"},
            },
            "required": ["doc", "instruction"],
        },
    },
    {
        "name": "revise_parse",
        "description": "解析修改操作的 LLM 响应，返回新的 DocumentTree。",
        "inputSchema": {
            "type": "object",
            "properties": {"llm_response": {"type": "string"}},
            "required": ["llm_response"],
        },
    },
]


def handle_tool_call(tool_name: str, arguments: dict) -> str:
    """处理 MCP tool 调用."""
    try:
        result = _dispatch(tool_name, arguments)
        if hasattr(result, "to_dict"):
            result = result.to_dict()
        return json.dumps({"ok": True, "data": result}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


def _dispatch(tool_name: str, args: dict):
    # ── Template ──
    if tool_name == "template_register_build":
        from paper_derived.engine.template import build_register_template_prompt
        sys_p, user_p = build_register_template_prompt(
            args["sample_text"], args["name"], args.get("description", "")
        )
        return {"system": sys_p, "user": user_p}

    if tool_name == "template_register_parse":
        from paper_derived.engine.template import parse_register_template_result
        return parse_register_template_result(
            args["llm_response"], args["name"], args.get("description", "")
        )

    if tool_name == "template_list":
        from paper_derived.engine.template import list_all
        return list_all()

    if tool_name == "template_show":
        from paper_derived.engine.template import get_template
        t = get_template(args["template_id"])
        if t is None:
            raise ValueError(f"模板不存在: {args['template_id']}")
        return t

    # ── Input ──
    if tool_name == "input_register_build":
        from paper_derived.engine.input_asset import build_register_input_prompt
        sys_p, user_p = build_register_input_prompt(args["raw_text"], args["name"])
        return {"system": sys_p, "user": user_p}

    if tool_name == "input_register_parse":
        from paper_derived.engine.input_asset import parse_register_input_result
        return parse_register_input_result(
            args["llm_response"], args["raw_text"], args["name"],
            args.get("source", "")
        )

    # ── Preflight ──
    if tool_name == "gen_preflight_build":
        from paper_derived.engine.generator import build_preflight_prompt
        assets = [InputAsset.from_dict(a) for a in args["input_assets"]]
        sys_p, user_p = build_preflight_prompt(assets, args["template_id"])
        return {"system": sys_p, "user": user_p}

    if tool_name == "gen_preflight_parse":
        from paper_derived.engine.generator import parse_preflight_result
        return parse_preflight_result(args["llm_response"])

    # ── Extract ──
    if tool_name == "gen_extract_build":
        from paper_derived.engine.generator import build_extract_prompt
        assets = [InputAsset.from_dict(a) for a in args["input_assets"]]
        sys_p, user_p = build_extract_prompt(assets, args["template_id"])
        return {"system": sys_p, "user": user_p}

    if tool_name == "gen_extract_parse":
        from paper_derived.engine.generator import parse_extract_result
        return parse_extract_result(args["llm_response"])

    # ── Generate ──
    if tool_name == "gen_generate_build":
        from paper_derived.engine.generator import build_generate_prompt
        assets = [InputAsset.from_dict(a) for a in args["input_assets"]]
        sys_p, user_p = build_generate_prompt(
            assets, args["template_id"], args.get("extraction_overrides")
        )
        return {"system": sys_p, "user": user_p}

    if tool_name == "gen_generate_parse":
        from paper_derived.engine.generator import parse_generate_result
        assets = [InputAsset.from_dict(a) for a in args["input_assets"]]
        return parse_generate_result(
            args["llm_response"], args["template_id"], assets
        )

    # ── Validate ──
    if tool_name == "gen_validate_build":
        from paper_derived.engine.validator import build_validate_prompt
        doc = DocumentTree.from_dict(args["doc"])
        sys_p, user_p = build_validate_prompt(doc, args["template_id"])
        return {"system": sys_p, "user": user_p}

    if tool_name == "gen_validate_parse":
        from paper_derived.engine.validator import parse_validate_result
        return parse_validate_result(args["llm_response"])

    # ── Revise ──
    if tool_name == "revise_section_build":
        from paper_derived.engine.doc_ops import build_revise_section_prompt
        doc = DocumentTree.from_dict(args["doc"])
        sys_p, user_p = build_revise_section_prompt(
            doc, args["section_id"], args["instruction"]
        )
        return {"system": sys_p, "user": user_p}

    if tool_name == "revise_global_build":
        from paper_derived.engine.doc_ops import build_revise_global_prompt
        doc = DocumentTree.from_dict(args["doc"])
        sys_p, user_p = build_revise_global_prompt(doc, args["instruction"])
        return {"system": sys_p, "user": user_p}

    if tool_name == "revise_parse":
        from paper_derived.engine.doc_ops import parse_revise_result
        return parse_revise_result(args["llm_response"])

    raise ValueError(f"未知 tool: {tool_name}")
