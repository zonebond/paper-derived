"""Paper Derived CLI — 引擎 prompt 构造入口.

CLI 只做两件事:
1. 构造 prompt: 读输入 → 调 build_xxx_prompt() → 输出 (system + user) 给 Agent
2. 解析结果: 读 LLM 响应 → 调 parse_xxx_result() → 输出数据模型

支持格式: .docx, .doc, .xlsx, .xls, .pdf, .pptx, .csv, .tsv, .md, .txt, .json
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from paper_derived.format_reader import read_file as _read_input_file


from paper_derived import __version__


@click.group()
@click.version_option(version=__version__, prog_name="paper-derived")
def main():
    """paper-derived — 文档生成引擎 (Agent 驱动).

    引擎不调 LLM。由 Agent (Claude Code / OpenCode / Pi) 负责:
    1. 调 paper-derived 命令获取 prompt
    2. 用自己的 LLM 执行
    3. 将 LLM 响应传给 paper-derived 解析
    """


@main.command("version")
def version_cmd():
    """输出完整版本信息（版本号、构建 commit、构建时间、能力清单）。"""
    from paper_derived import get_version_info
    from paper_derived.engine._paths import PROMPTS_DIR

    info = get_version_info()
    info["compact_prompts"] = (PROMPTS_DIR / "compact").is_dir()
    info["capabilities"] = ["out-text-prompt", "parse-output-file", "session-run", "llm-exec", "compact-prompts", "doc-export", "doc-sanitize", "pd-workdir", "template-register-auto", "gen-run", "guidance-slices", "placeholder-fallback", "structure-audit", "claude-cli-provider", "cmd-provider", "llm-config"]
    click.echo(json.dumps(info, ensure_ascii=False))


# ── Output helpers ─────────────────────────────────────────────


PROMPT_SYSTEM_MARKER = "==== SYSTEM ===="
PROMPT_USER_MARKER = "==== USER ===="


def _write_prompt_text(path: str | Path, system_prompt: str, user_message: str) -> None:
    """将 prompt 写为纯文本文件（真实换行）.

    不用 JSON：JSON 会把整个 prompt 压成单行超长字符串，Agent 的文件读取工具
    对超长行会截断，导致子代理拿到残缺 prompt。文本格式用分隔符区分两段：

        ==== SYSTEM ====
        <系统指令>

        ==== USER ====
        <任务>
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"{PROMPT_SYSTEM_MARKER}\n{system_prompt}\n\n{PROMPT_USER_MARKER}\n{user_message}\n",
        encoding="utf-8",
    )


def _prompt_summary(prompt_file: str, system_prompt: str, user_message: str) -> dict:
    summary = {
        "status": "prompt_written",
        "prompt_file": str(prompt_file),
    }
    try:
        from paper_derived.engine._tokens import count_tokens
        summary["prompt_tokens"] = count_tokens(system_prompt) + count_tokens(user_message)
    except Exception:
        summary["prompt_chars"] = len(system_prompt) + len(user_message)
    return summary


def _output_prompt(system_prompt: str, user_message: str, prompt_file: str | None = None) -> None:
    """输出 prompt 供 Agent 消费.

    当 prompt_file 指定时，将 prompt 写为纯文本文件，stdout 仅输出紧凑摘要。
    不指定时输出 JSON 到 stdout（向后兼容；会灌满 Agent 上下文，不推荐）。
    """
    if prompt_file:
        _write_prompt_text(prompt_file, system_prompt, user_message)
        click.echo(json.dumps(_prompt_summary(prompt_file, system_prompt, user_message), ensure_ascii=False))
    else:
        click.echo(json.dumps({
            "system": system_prompt,
            "user": user_message,
        }, ensure_ascii=False, indent=2))


def _out_option(f):
    """`--out`（别名 `--prompt-file`）：prompt 落盘选项，全命令统一."""
    return click.option(
        "--out", "--prompt-file", "prompt_file",
        default=None, type=click.Path(),
        help="将 prompt 写入文本文件而非 stdout（子代理委托必用，防止撑爆主上下文）",
    )(f)


def _output_json(obj) -> None:
    """输出 JSON 结果."""
    if hasattr(obj, "to_dict"):
        obj = obj.to_dict()
    click.echo(json.dumps(obj, ensure_ascii=False, indent=2))


def _write_result_json(obj, output: str) -> None:
    """将结果 JSON 写入文件（主 Agent 只拿路径，不接内容）."""
    if hasattr(obj, "to_dict"):
        obj = obj.to_dict()
    p = Path(output)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _output_asset(result, output: str | None, asset_name: str, slim: bool) -> None:
    """输出 InputAsset：有 -O 时写文件 + 状态摘要，否则全量 stdout（兼容，不推荐）."""
    if output:
        _write_result_json(result, output)
        click.echo(json.dumps({
            "status": "asset_written",
            "asset_file": str(output),
            "name": asset_name,
            "entities": len(getattr(result, "entities", []) or []),
            "summary_chars": len(getattr(result, "summary", "") or ""),
            "slim": slim,
        }, ensure_ascii=False))
    else:
        _output_json(result)


def _llm_client_options(f):
    """直驱模式的 provider 连接选项（session run / llm exec 共用）."""
    f = click.option("--api-base", default="", envvar="PAPER_DERIVED_API_BASE",
                     help="LLM 端点：OpenAI 兼容地址（生产环境通常是远程服务）、claude-cli、"
                          "或 cmd:<agent命令>。未给出时用 `llm config` 的持久化配置")(f)
    f = click.option("--model", "-m", default="", envvar="PAPER_DERIVED_MODEL",
                     help="模型名，如 qwen2.5:14b；claude-cli 时可用 sonnet/haiku/opus（留空用默认）")(f)
    f = click.option("--api-key", default="", envvar="PAPER_DERIVED_API_KEY",
                     help="API Key（本地 provider 通常不需要）")(f)
    f = click.option("--temperature", default=0.2, type=float, help="采样温度（默认 0.2）")(f)
    f = click.option("--max-output", default=4096, type=int,
                     help="单次调用的最大输出 token（默认 4096）")(f)
    f = click.option("--timeout", default=600.0, type=float, help="单次调用超时秒数")(f)
    return f


def _make_client(api_base, model, api_key, temperature, max_output, timeout):
    from paper_derived.llm import make_client, ProviderNotConfigured
    try:
        return make_client(
            api_base, model, api_key=api_key,
            temperature=temperature, max_output_tokens=max_output, timeout=timeout,
        )
    except ProviderNotConfigured as e:
        raise click.UsageError(str(e))


# ── Template commands ──────────────────────────────────────────


@main.group()
def template():
    """模板管理."""


@template.command("register")
@click.argument("sample", type=click.Path(exists=True))
@click.option("--name", "-n", required=True, help="模板名称 (kebab-case)")
@click.option("--description", "-d", default="", help="模板描述")
@click.option("--parse", "-p", default=None, type=click.Path(exists=True),
              help="解析 LLM 响应文件 (而非输出 prompt)")
@_out_option
def template_register(sample, name, description, parse, prompt_file):
    """注册模板: 输出分析 prompt，或解析 LLM 响应."""
    from paper_derived.engine.template import (
        build_register_template_prompt,
        parse_register_template_result,
        _to_kebab_case,
    )
    from paper_derived.llm import extract_json
    from paper_derived.storage import find_template_by_name, template_exists

    # 精确同名检查：同名模板已存在时报错拦截
    existing = find_template_by_name(name)
    if existing:
        click.echo(json.dumps({
            "error": "template_name_exists",
            "message": f"模板「{name}」已存在（id: {existing.id}）",
            "existing_id": existing.id,
        }, ensure_ascii=False))
        raise SystemExit(1)

    if parse:
        llm_response = Path(parse).read_text(encoding="utf-8")

        # id 冲突检查：LLM 可能生成与已有模板相同的 id
        parsed = extract_json(llm_response)
        resolved_id = _to_kebab_case(parsed.get("id", name))
        if template_exists(resolved_id):
            existing_name = ""
            existing_tpl = find_template_by_name(name)  # 已在上面检查过，这里不会命中
            from paper_derived.storage import load_template
            existing_tpl = load_template(resolved_id)
            existing_name = existing_tpl.name if existing_tpl else ""
            click.echo(json.dumps({
                "error": "template_id_exists",
                "message": f"模板 id「{resolved_id}」已存在（名称: {existing_name}）",
                "existing_id": resolved_id,
                "existing_name": existing_name,
            }, ensure_ascii=False))
            raise SystemExit(1)

        sample_text, _, _ = _read_input_file(sample)
        result = parse_register_template_result(llm_response, name, description, sample_text=sample_text)
        # 模板已由 parse_register_template_result 存入 storage；stdout 只报摘要，
        # 完整定义用 `template show <id>` 查看，避免整个模板 JSON 灌进 Agent 上下文
        summary = {
            "status": "template_registered",
            "template_id": result.id,
            "name": result.name,
            "sections": len(result.section_ids),
            "section_ids": result.section_ids,
        }
        auto_added = getattr(result, "auto_added_sections", [])
        if auto_added:
            summary["auto_added_sections"] = auto_added
            summary["warning"] = (
                f"LLM 遗漏了 {len(auto_added)} 个一级章节，已按结构预扫描锚点自动补回骨架"
                "（dependency 默认 self_contained，可用 template show 检查后手动调整）"
            )
        click.echo(json.dumps(summary, ensure_ascii=False))
    else:
        sample_text, _, _ = _read_input_file(sample)
        sys_prompt, user_msg = build_register_template_prompt(sample_text, name, description)
        _output_prompt(sys_prompt, user_msg, prompt_file=prompt_file)


@template.command("register-auto")
@click.argument("sample", type=click.Path(exists=True))
@click.option("--name", "-n", required=True, help="模板名称")
@click.option("--description", "-d", default="", help="模板描述")
@_llm_client_options
@click.option("--window", default=0, type=int, help="Provider 上下文窗口（token），控制样例节选长度")
@click.option("--compact", is_flag=True, default=False, help="使用精简版内置 prompt")
def template_register_auto(sample, name, description, api_base, model, api_key,
                           temperature, max_output, timeout, window, compact):
    """小模型友好的模板注册（直驱）：结构确定性扫描，LLM 只写三段小文本。

    章节树由引擎从样例的编号/markdown 标题确定性构建（不让 LLM 输出大 JSON），
    structure 模块确定性渲染；LLM 仅执行 3 次纯文本小调用（抽取/风格/校验指令）。
    ~30B 级模型可稳定完成。
    """
    from paper_derived.runner import register_template_auto, PipelineError

    if compact:
        from paper_derived.engine._paths import set_compact
        set_compact(True)

    sample_text, _, _ = _read_input_file(sample)
    client = _make_client(api_base, model, api_key, temperature, max_output, timeout)

    def on_event(ev: dict) -> None:
        click.echo(json.dumps(ev, ensure_ascii=False))

    try:
        tpl = register_template_auto(sample_text, name, description, client,
                                     window=window, on_event=on_event)
    except PipelineError as e:
        click.echo(json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False))
        raise SystemExit(1)
    click.echo(json.dumps({
        "status": "template_registered",
        "template_id": tpl.id,
        "sections": len(tpl.section_ids),
        "section_ids": tpl.section_ids,
        "structure_source": "deterministic-scan",
    }, ensure_ascii=False))


@template.command("list")
@click.option("--json", "as_json", is_flag=True, help="输出 JSON 格式（含 section_ids）")
def template_list(as_json):
    """列出所有模板."""
    from paper_derived.engine.template import list_all
    templates = list_all()
    if not templates:
        click.echo("(暂无已注册模板)")
        return
    if as_json:
        click.echo(json.dumps(templates, ensure_ascii=False, indent=2))
        return
    click.echo(f"{'ID':<24} {'名称':<20} 描述")
    click.echo("-" * 64)
    for t in templates:
        click.echo(f"{t['id']:<24} {t['name']:<20} {t.get('description', '')}")


@template.command("show")
@click.argument("template_id")
def template_show(template_id):
    """查看模板详情."""
    from paper_derived.engine.template import get_template
    result = get_template(template_id)
    if result is None:
        click.echo(f"模板 '{template_id}' 不存在")
        raise SystemExit(1)
    _output_json(result)


@template.command("delete")
@click.argument("template_id")
def template_delete(template_id):
    """删除模板."""
    from paper_derived.storage import template_exists, delete_template

    if not template_exists(template_id):
        click.echo(f"模板 '{template_id}' 不存在")
        raise SystemExit(1)
    delete_template(template_id)
    click.echo(f"模板 '{template_id}' 已删除")


# ── Input commands ─────────────────────────────────────────────


@main.group()
def input():
    """输入资产管理."""


@input.command("register")
@click.argument("file", type=click.Path(exists=True))
@click.option("--name", "-n", default=None, help="资产名称")
@click.option("--parse", "-p", default=None, type=click.Path(exists=True),
              help="解析 LLM 响应文件")
@click.option("--chunk-size", default=0, type=int,
              help="分块大小(字符数)。0=不分块。大于0时输出分块 prompts。")
@click.option("--parse-chunks", multiple=True, type=click.Path(exists=True),
              help="解析分块 LLM 响应文件(可多次指定)。合并为单个 InputAsset。")
@click.option("--slim/--no-slim", default=True,
              help="精简模式：不存储 raw_content，仅保留摘要和实体。（默认开启，大文档推荐）")
@click.option("--output", "-O", default=None, type=click.Path(),
              help="解析模式：InputAsset JSON 写入该文件，stdout 仅输出状态摘要（推荐，防止灌主上下文）")
@_out_option
def input_register(file, name, parse, chunk_size, parse_chunks, slim, output, prompt_file):
    """注册输入资产: 输出分析 prompt，或解析 LLM 响应.

    大文档自动分块：用 --chunk-size 指定每块最大字符数（建议 30000），
    输出多个 prompt 供逐块处理，再用 --parse-chunks 合并结果。

    默认 --slim：不存储 raw_content，仅保留摘要和实体列表，
    避免输出 JSON 过大。下游命令会基于实体列表而非原文生成。
    使用 --no-slim 保留 raw_content（大文档不推荐）。
    """
    from paper_derived.engine.input_asset import (
        build_register_input_prompt,
        build_register_input_chunk_prompt,
        parse_register_input_result,
        merge_input_assets,
    )
    from paper_derived.format_reader import chunk_text, DEFAULT_CHUNK_SIZE

    raw, fmt_type, metadata = _read_input_file(file)
    asset_name = name or Path(file).stem

    # 解析分块结果并合并
    if parse_chunks:
        partial_assets = []
        for resp_path in parse_chunks:
            llm_response = Path(resp_path).read_text(encoding="utf-8")
            partial = parse_register_input_result(llm_response, "", asset_name, source=file, slim=slim)
            partial_assets.append(partial)
        result = merge_input_assets(partial_assets, raw if not slim else "", asset_name, source=file, slim=slim)
        _output_asset(result, output, asset_name, slim)
        return

    # 解析单块结果
    if parse:
        llm_response = Path(parse).read_text(encoding="utf-8")
        result = parse_register_input_result(llm_response, raw if not slim else "", asset_name, source=file, slim=slim)
        _output_asset(result, output, asset_name, slim)
        return

    # 构造 prompt（分块 or 整体）
    effective_chunk_size = chunk_size if chunk_size > 0 else DEFAULT_CHUNK_SIZE
    chunks = chunk_text(raw, max_chars=effective_chunk_size)

    if len(chunks) == 1:
        # 文档不大，输出单个 prompt
        sys_prompt, user_msg = build_register_input_prompt(raw, asset_name)
        _output_prompt(sys_prompt, user_msg, prompt_file=prompt_file)
    else:
        # 大文档，输出分块 prompt
        from paper_derived.engine._tokens import count_tokens

        if prompt_file:
            # --out 模式：每块写入独立文本文件 <stem>.chunk-<i><suffix>
            base = Path(prompt_file)
            suffix = base.suffix or ".md"
            chunk_files = []
            total_tokens = 0
            for i, chunk in enumerate(chunks):
                sys_prompt, user_msg = build_register_input_chunk_prompt(
                    chunk, asset_name, chunk_index=i, total_chunks=len(chunks)
                )
                chunk_file = str(base.with_name(f"{base.stem}.chunk-{i}{suffix}"))
                _write_prompt_text(chunk_file, sys_prompt, user_msg)
                chunk_tokens = count_tokens(sys_prompt) + count_tokens(user_msg)
                total_tokens += chunk_tokens
                chunk_files.append(chunk_file)
            click.echo(json.dumps({
                "status": "prompts_written",
                "mode": "chunked",
                "total_chunks": len(chunks),
                "prompt_files": chunk_files,
                "total_prompt_tokens": total_tokens,
            }, ensure_ascii=False))
        else:
            # 原有行为：全部输出到 stdout
            chunk_prompts = []
            for i, chunk in enumerate(chunks):
                sys_prompt, user_msg = build_register_input_chunk_prompt(
                    chunk, asset_name, chunk_index=i, total_chunks=len(chunks)
                )
                chunk_prompts.append({
                    "index": i,
                    "system": sys_prompt,
                    "user": user_msg,
                })
            click.echo(json.dumps({
                "mode": "chunked",
                "total_chunks": len(chunks),
                "chunk_size": effective_chunk_size,
                "chunks": chunk_prompts,
            }, ensure_ascii=False, indent=2))


# ── Generate commands ──────────────────────────────────────────


@main.group()
def gen():
    """文档生成：资料体检 → 实体抽取 → 文档生成."""


def _load_input_assets(file_paths: list[str]) -> list:
    """加载已注册的 InputAsset JSON 文件.

    只接受 .json（由 `input register` 产出）。不接受原始文件——原始文件必须先注册。
    """
    from paper_derived.models.input_asset import InputAsset

    assets = []
    for fp in file_paths:
        p = Path(fp)
        if p.suffix != ".json":
            raise click.UsageError(
                f"不接受原始文件 '{fp}'。请先注册输入资产:\n"
                f"  paper-derived input register '{fp}' -n <资产名称>\n"
                f"然后使用注册后产出的 .json 文件作为 -i 参数。"
            )
        data = json.loads(p.read_text(encoding="utf-8"))
        assets.append(InputAsset.from_dict(data))
    return assets


@gen.command("preflight")
@click.option("--inputs", "-i", required=True, multiple=True, type=click.Path(exists=True))
@click.option("--template", "-t", required=True, help="模板 ID")
@click.option("--parse", "-p", default=None, type=click.Path(exists=True),
              help="解析 LLM 响应文件")
@_out_option
def gen_preflight(inputs, template, parse, prompt_file):
    """资料体检."""
    from paper_derived.engine.generator import build_preflight_prompt, parse_preflight_result

    assets = _load_input_assets(list(inputs))

    if parse:
        result = parse_preflight_result(Path(parse).read_text(encoding="utf-8"))
        _output_json(result)
    else:
        sys_prompt, user_msg = build_preflight_prompt(assets, template)
        _output_prompt(sys_prompt, user_msg, prompt_file=prompt_file)


@gen.command("extract")
@click.option("--inputs", "-i", required=True, multiple=True, type=click.Path(exists=True))
@click.option("--template", "-t", required=True, help="模板 ID")
@click.option("--parse", "-p", default=None, type=click.Path(exists=True),
              help="解析 LLM 响应文件")
@click.option("--output", "-O", default=None, type=click.Path(),
              help="解析模式：抽取结果 JSON 写入该文件，stdout 仅输出状态摘要")
@_out_option
def gen_extract(inputs, template, parse, output, prompt_file):
    """实体抽取."""
    from paper_derived.engine.generator import build_extract_prompt, parse_extract_result

    assets = _load_input_assets(list(inputs))

    if parse:
        result = parse_extract_result(Path(parse).read_text(encoding="utf-8"))
        if output:
            _write_result_json(result, output)
            sections = getattr(result, "sections", []) or []
            click.echo(json.dumps({
                "status": "extract_written",
                "output": str(output),
                "summary": getattr(result, "summary", ""),
                "sections": len(sections),
                "items": sum(len(getattr(s, "found", []) or []) for s in sections),
                "warnings": getattr(result, "warnings", []) or [],
            }, ensure_ascii=False))
        else:
            _output_json(result)
    else:
        sys_prompt, user_msg = build_extract_prompt(assets, template)
        _output_prompt(sys_prompt, user_msg, prompt_file=prompt_file)


@gen.command("outline")
@click.option("--template", "-t", required=True, help="模板 ID")
@click.option("--output", "-O", default=None, help="输出文件路径")
@click.option("--format", "-f", "output_format", default=None,
              help="输出格式: json|md|docx|pdf（默认从 --output 扩展名推断）")
@click.option("--parse", "-p", default=None, type=click.Path(exists=True),
              help="解析 LLM 响应文件")
@_out_option
def gen_outline(template, output, output_format, parse, prompt_file):
    """生成文档大纲（骨架）。"""
    from paper_derived.engine.generator import build_outline_prompt, parse_outline_result
    from paper_derived.format_writer import write_document

    if parse:
        result = parse_outline_result(Path(parse).read_text(encoding="utf-8"), template)
        if output:
            out_path = write_document(result, output, fmt=output_format)
            click.echo(f"已输出大纲 → {out_path}")
        else:
            _output_json(result)
    else:
        sys_prompt, user_msg = build_outline_prompt(template)
        _output_prompt(sys_prompt, user_msg, prompt_file=prompt_file)


@gen.command("generate")
@click.option("--inputs", "-i", required=True, multiple=True, type=click.Path(exists=True))
@click.option("--template", "-t", required=True, help="模板 ID")
@click.option("--overrides", "-o", default=None, type=click.Path(exists=True))
@click.option("--sections", "-s", default=None, help="逗号分隔的 Section ID 列表（分批生成时指定）")
@click.option("--extract", "-e", default=None, type=click.Path(exists=True),
              help="抽取结果 JSON（分批生成时用于筛选实体）")
@click.option("--into", default=None, type=click.Path(exists=True),
              help="已有文档树路径（分批生成时合并到该文档）")
@click.option("--output", "-O", default=None, help="输出文件路径")
@click.option("--format", "-f", "output_format", default=None,
              help="输出格式: json|md|docx|pdf（默认从 --output 扩展名推断）")
@click.option("--parse", "-p", default=None, type=click.Path(exists=True),
              help="解析 LLM 响应文件")
@_out_option
def gen_generate(inputs, template, overrides, sections, extract, into, output, output_format, parse, prompt_file):
    """生成文档树。支持全量或分批生成。"""
    from paper_derived.engine.generator import (
        build_generate_prompt, parse_generate_result,
        build_batch_generate_prompt, parse_batch_generate_result,
    )
    from paper_derived.format_writer import write_document
    from paper_derived.models.extraction import ExtractionResult

    assets = _load_input_assets(list(inputs))
    extraction_overrides = None
    if overrides:
        extraction_overrides = json.loads(Path(overrides).read_text(encoding="utf-8"))

    # 分批生成模式
    if sections:
        section_ids = [s.strip() for s in sections.split(",") if s.strip()]
        extraction_result = None
        if extract:
            extraction_data = json.loads(Path(extract).read_text(encoding="utf-8"))
            extraction_result = ExtractionResult.from_dict(extraction_data)

        existing_doc = None
        if into:
            doc_data = json.loads(Path(into).read_text(encoding="utf-8"))
            from paper_derived.models.document import DocumentTree
            existing_doc = DocumentTree.from_dict(doc_data)

        if parse:
            result = parse_batch_generate_result(
                Path(parse).read_text(encoding="utf-8"), template, assets
            )
            if existing_doc:
                merged_count = existing_doc.merge_batch(result)
                result = existing_doc
                click.echo(f"批量合并: 更新了 {merged_count} 个 section", err=True)
            if output:
                out_path = write_document(result, output, fmt=output_format)
                click.echo(f"已输出 → {out_path}")
            else:
                _output_json(result)
        else:
            sys_prompt, user_msg = build_batch_generate_prompt(
                assets, template, section_ids, extraction_result, existing_doc,
            )
            _output_prompt(sys_prompt, user_msg, prompt_file=prompt_file)
        return

    # 全量生成模式（原有逻辑）
    if parse:
        result = parse_generate_result(
            Path(parse).read_text(encoding="utf-8"), template, assets
        )
        if output:
            out_path = write_document(result, output, fmt=output_format)
            click.echo(f"已输出 → {out_path}")
        else:
            _output_json(result)
    else:
        sys_prompt, user_msg = build_generate_prompt(assets, template, extraction_overrides)
        _output_prompt(sys_prompt, user_msg, prompt_file=prompt_file)


@gen.command("validate")
@click.argument("doc", type=click.Path(exists=True))
@click.option("--template", "-t", required=True, help="模板 ID")
@click.option("--parse", "-p", default=None, type=click.Path(exists=True),
              help="解析 LLM 响应文件")
@_out_option
def gen_validate(doc, template, parse, prompt_file):
    """质检."""
    from paper_derived.engine.validator import build_validate_prompt, parse_validate_result
    from paper_derived.models.document import DocumentTree

    doc_data = json.loads(Path(doc).read_text(encoding="utf-8"))
    doc_tree = DocumentTree.from_dict(doc_data)

    if parse:
        result = parse_validate_result(Path(parse).read_text(encoding="utf-8"))
        _output_json(result)
    else:
        sys_prompt, user_msg = build_validate_prompt(doc_tree, template)
        _output_prompt(sys_prompt, user_msg, prompt_file=prompt_file)


# ── Doc commands ───────────────────────────────────────────────


@main.group()
def doc():
    """文档树操作（确定性，无需 LLM）."""


@doc.command("sanitize")
@click.argument("doc_file", type=click.Path(exists=True))
@click.option("--output", "-O", default=None, type=click.Path(),
              help="净化后写入路径（默认原地覆盖）")
def doc_sanitize(doc_file, output):
    """净化已有 DocumentTree：清除各节 content 中的 markdown 标题行。

    修复历史生成结果的结构污染（层级错乱/硬编码编号/多余子结构/重复标题），
    无需重新生成。规则同引擎解析路径：重复标题删除、子节子树截断、
    自创子结构降级为加粗小标题。之后可用 doc export 重新渲染交付文件。
    """
    from paper_derived.models.document import DocumentTree

    tree = DocumentTree.from_dict(json.loads(Path(doc_file).read_text(encoding="utf-8")))
    before = json.dumps(tree.to_dict(), ensure_ascii=False)
    tree.sanitize_headings()
    after_dict = tree.to_dict()
    out_path = output or doc_file
    _write_result_json(after_dict, out_path)
    click.echo(json.dumps({
        "status": "sanitized",
        "output": str(out_path),
        "changed": json.dumps(after_dict, ensure_ascii=False) != before,
    }, ensure_ascii=False))


@doc.command("export")
@click.argument("doc_file", type=click.Path(exists=True))
@click.option("--output", "-O", required=True, help="交付文件路径（建议写在项目根，不要放 .pd/ 里）")
@click.option("--format", "-f", "output_format", default=None,
              help="输出格式: md|docx|pdf|json（默认从扩展名推断）")
def doc_export(doc_file, output, output_format):
    """把 DocumentTree JSON（.pd/output.json / .pd/doc.json）渲染为交付文件。"""
    from paper_derived.models.document import DocumentTree
    from paper_derived.format_writer import write_document

    tree = DocumentTree.from_dict(json.loads(Path(doc_file).read_text(encoding="utf-8")))
    out_path = write_document(tree, output, fmt=output_format)
    click.echo(json.dumps({"status": "exported", "output": str(out_path)}, ensure_ascii=False))


@gen.command("run")
@click.option("--template", "-t", required=True, help="模板 ID")
@click.option("--inputs", "-i", "input_files", required=True, multiple=True,
              type=click.Path(exists=True), help="原始输入资料（可多个，非 InputAsset JSON）")
@_llm_client_options
@click.option("--window", default=0, type=int,
              help="Provider 上下文窗口（token）。自动推导 chunk 大小与 session 预算")
@click.option("--compact", is_flag=True, default=False, help="使用精简版内置 prompt（小模型推荐）")
@click.option("--workdir", default=".pd", type=click.Path(), help="过程文件目录（默认 .pd）")
@click.option("--max-sections", default=0, type=int, help="本次最多生成的 Section 数（0=不限）")
@click.option("--no-summarize", "no_summarize", is_flag=True, default=False)
@click.option("--max-attempts", default=3, type=int, help="每步最大尝试次数（含格式修复重试）")
@click.option("--placeholders/--no-placeholders", "placeholders", default=True,
              help="缺输入/生成失败的节由引擎直接写占位说明（默认开——保证结构绝不缺失）")
@click.option("--output", "-O", default="", help="交付文件路径（如 output.md / output.docx）")
@click.option("--format", "-f", "output_format", default=None, help="输出格式: md|docx|pdf|json")
def gen_run(template, input_files, api_base, model, api_key, temperature, max_output,
            timeout, window, compact, workdir, max_sections, no_summarize,
            max_attempts, placeholders, output, output_format):
    """一条龙直驱生成：原始资料 → 注册（自动分块）→ feed → 逐节生成 → 组装交付。

    全程引擎调 Provider，零 Agent 编排；~30B 级模型可稳定完成。
    可断点续传：已注册资产跳过，session 进度由 checkpoint 托管，
    中断后重跑同一条命令即继续。
    """
    from paper_derived.runner import run_pipeline, PipelineError

    if compact:
        from paper_derived.engine._paths import set_compact
        set_compact(True)

    client = _make_client(api_base, model, api_key, temperature, max_output, timeout)

    def on_event(ev: dict) -> None:
        click.echo(json.dumps(ev, ensure_ascii=False))

    try:
        summary = run_pipeline(
            template, list(input_files), client,
            window=window, workdir=workdir, output=output,
            output_format=output_format, max_sections=max_sections,
            do_summarize=not no_summarize, max_attempts=max_attempts,
            placeholders=placeholders, on_event=on_event,
        )
    except PipelineError as e:
        click.echo(json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False))
        raise SystemExit(1)
    if summary["status"] in ("stuck",) or summary["failed"]:
        raise SystemExit(1)


# ── Revise commands ────────────────────────────────────────────


@main.group()
def revise():
    """文档修改：局部/全局改写."""


@revise.command("section")
@click.argument("doc", type=click.Path(exists=True))
@click.argument("section_id")
@click.argument("instruction")
@click.option("--output", "-O", default=None, help="输出文件路径")
@click.option("--format", "-f", "output_format", default=None,
              help="输出格式: json|md|docx|pdf（默认从 --output 扩展名推断）")
@click.option("--parse", "-p", default=None, type=click.Path(exists=True),
              help="解析 LLM 响应文件")
@_out_option
def revise_section_cmd(doc, section_id, instruction, output, output_format, parse, prompt_file):
    """局部修改."""
    from paper_derived.engine.doc_ops import build_revise_section_prompt, parse_revise_result
    from paper_derived.models.document import DocumentTree
    from paper_derived.format_writer import write_document

    doc_data = json.loads(Path(doc).read_text(encoding="utf-8"))
    doc_tree = DocumentTree.from_dict(doc_data)

    if parse:
        result = parse_revise_result(Path(parse).read_text(encoding="utf-8"))
        out_path = output or doc
        write_document(result, out_path, fmt=output_format)
        click.echo(f"已修改 section='{section_id}' → {out_path}")
    else:
        sys_prompt, user_msg = build_revise_section_prompt(doc_tree, section_id, instruction)
        _output_prompt(sys_prompt, user_msg, prompt_file=prompt_file)


@revise.command("global")
@click.argument("doc", type=click.Path(exists=True))
@click.argument("instruction")
@click.option("--output", "-O", default=None, help="输出文件路径")
@click.option("--format", "-f", "output_format", default=None,
              help="输出格式: json|md|docx|pdf（默认从 --output 扩展名推断）")
@click.option("--parse", "-p", default=None, type=click.Path(exists=True),
              help="解析 LLM 响应文件")
@_out_option
def revise_global_cmd(doc, instruction, output, output_format, parse, prompt_file):
    """全局改写."""
    from paper_derived.engine.doc_ops import build_revise_global_prompt, parse_revise_result
    from paper_derived.models.document import DocumentTree
    from paper_derived.format_writer import write_document

    doc_data = json.loads(Path(doc).read_text(encoding="utf-8"))
    doc_tree = DocumentTree.from_dict(doc_data)

    if parse:
        result = parse_revise_result(Path(parse).read_text(encoding="utf-8"))
        out_path = output or doc
        write_document(result, out_path, fmt=output_format)
        click.echo(f"已全局修改 → {out_path}")
    else:
        sys_prompt, user_msg = build_revise_global_prompt(doc_tree, instruction)
        _output_prompt(sys_prompt, user_msg, prompt_file=prompt_file)


# ── Session commands ────────────────────────────────────────────


@main.group()
def session():
    """会话驱动生成 (Session-Driven Generation).

    结构化任务迭代 + 全局状态，破解上下文爆炸与长任务失控。
    CLI 内部维护 ContextStore，Agent 只发声明式命令。
    """


@session.command("init")
@click.option("--template", "-t", required=True, help="模板 ID")
@click.option("--budget", default=60_000, type=int,
              help="per-section token 预算（默认 60000；prompt 由子代理执行，预算越大子代理负载越重）")
@click.option("--output", "-O", default="", help="最终输出文件路径")
@click.option("--format", "-f", "output_format", default="", help="输出格式")
def session_init_cmd(template, budget, output, output_format):
    """初始化生成会话."""
    from paper_derived.engine.session_engine import session_init

    result = session_init(template, budget, output, output_format)
    _output_json({
        "session_id": result.session_id,
        "template_id": result.template_id,
        "phase": result.phase,
        "total_sections": result.total_sections,
        "section_ids": list(result.section_progress.keys()),
    })


@session.command("feed")
@click.option("--session-id", "-s", required=True, help="Session ID")
@click.option("--input", "-i", "inputs", required=True, multiple=True,
              type=click.Path(exists=True), help="InputAsset JSON 文件")
@click.option("--parse", "-p", default=None, type=click.Path(exists=True),
              help="解析 LLM 响应文件")
@_out_option
def session_feed_cmd(session_id, inputs, parse, prompt_file):
    """喂入输入资产，填充上下文库。Agent 只看到状态报告。"""
    from paper_derived.engine.session_engine import build_feed_prompt, parse_feed_result

    if parse:
        result = parse_feed_result(Path(parse).read_text(encoding="utf-8"), session_id)
        _output_json(result)
    else:
        from paper_derived.session_store import load_session
        session_obj, _, _ = load_session(session_id)
        input_assets = []
        for fp in inputs:
            data = json.loads(Path(fp).read_text(encoding="utf-8"))
            input_assets.append(data)
        sys_prompt, user_msg = build_feed_prompt(session_obj, input_assets)
        _output_prompt(sys_prompt, user_msg, prompt_file=prompt_file)


@session.command("next")
@click.option("--session-id", "-s", required=True, help="Session ID")
def session_next_cmd(session_id):
    """查询下一步操作。无需 LLM。"""
    from paper_derived.engine.session_engine import session_next

    result = session_next(session_id)
    _output_json(result)


@session.command("prompt")
@click.option("--session-id", "-s", required=True, help="Session ID")
@click.option("--section", required=True, help="Section ID")
@click.option("--parse", "-p", default=None, type=click.Path(exists=True),
              help="解析 LLM 响应文件")
@_out_option
def session_prompt_cmd(session_id, section, parse, prompt_file):
    """获取 Section 生成 prompt (CLI 自动组装上下文)。"""
    from paper_derived.engine.session_engine import build_section_prompt, parse_section_result

    if parse:
        result = parse_section_result(Path(parse).read_text(encoding="utf-8"), session_id, section)
        _output_json(result)
    else:
        sys_prompt, user_msg = build_section_prompt(session_id, section)
        _output_prompt(sys_prompt, user_msg, prompt_file=prompt_file)


@session.command("summarize")
@click.option("--session-id", "-s", required=True, help="Session ID")
@click.option("--section", required=True, help="Section ID")
@click.option("--parse", "-p", default=None, type=click.Path(exists=True),
              help="解析 LLM 响应文件")
@_out_option
def session_summarize_cmd(session_id, section, parse, prompt_file):
    """生成 Section 摘要 (存入内部 ContextStore, Agent 不可见)。"""
    from paper_derived.engine.session_engine import build_summarize_prompt, parse_summarize_result

    if parse:
        result = parse_summarize_result(Path(parse).read_text(encoding="utf-8"), session_id, section)
        _output_json(result)
    else:
        sys_prompt, user_msg = build_summarize_prompt(session_id, section)
        _output_prompt(sys_prompt, user_msg, prompt_file=prompt_file)


@session.command("assemble")
@click.option("--session-id", "-s", required=True, help="Session ID")
@click.option("--output", "-O", default=None, help="输出文件路径")
@click.option("--format", "-f", "output_format", default=None,
              help="输出格式: md|docx|pdf|json")
def session_assemble_cmd(session_id, output, output_format):
    """组装最终文档 (解析交叉引用, 无需 LLM)。"""
    from paper_derived.engine.session_engine import session_assemble
    from paper_derived.format_writer import write_document

    doc = session_assemble(session_id)

    if output:
        out_path = write_document(doc, output, fmt=output_format)
        click.echo(f"已输出 → {out_path}")
    else:
        _output_json(doc)


@session.command("status")
@click.option("--session-id", "-s", required=True, help="Session ID")
def session_status_cmd(session_id):
    """查看会话状态。无需 LLM。"""
    from paper_derived.engine.session_engine import session_status

    result = session_status(session_id)
    _output_json(result)


@session.command("search")
@click.option("--session-id", "-s", required=True, help="Session ID")
@click.argument("query")
@click.option("--focus", default="", help="聚焦到指定 entity_key 获取完整详情")
@click.option("--budget", default=2000, type=int, help="返回结果的 token 预算上限")
def session_search_cmd(session_id, query, focus, budget):
    """搜索上下文库（带 token 预算防护）。无需 LLM。"""
    from paper_derived.engine.session_engine import session_search

    result = session_search(session_id, query, focus=focus, budget=budget)
    _output_json(result)


@session.command("run")
@click.option("--session-id", "-s", required=True, help="Session ID")
@_llm_client_options
@click.option("--window", default=0, type=int,
              help="Provider 上下文窗口（token）。指定后自动收缩预算：budget = min(现值, window/2)")
@click.option("--max-sections", default=0, type=int,
              help="本次最多生成的 Section 数（0=不限）。用于人工分段审查")
@click.option("--summarize/--no-summarize", "do_summarize", default=True,
              help="每节生成后自动摘要入 ContextStore（默认开，控制下游 prompt 体积）")
@click.option("--max-attempts", default=3, type=int, help="单 Section 最大尝试次数（含格式修复重试）")
@click.option("--compact", is_flag=True, default=False,
              help="使用精简版内置 prompt（小模型推荐；其他命令用 PAPER_DERIVED_COMPACT=1 开启）")
@click.option("--placeholders", is_flag=True, default=False,
              help="缺输入/生成失败的节由引擎直接写占位说明，不停下（gen run 默认开，此处默认关）")
@click.option("--assemble/--no-assemble", "do_assemble", default=True,
              help="全部完成后自动组装（默认开）")
@click.option("--output", "-O", default=None, help="组装输出文件路径（默认用 session init 时的配置）")
@click.option("--format", "-f", "output_format", default=None, help="输出格式: md|docx|pdf|json")
def session_run_cmd(session_id, api_base, model, api_key, temperature, max_output, timeout,
                    window, max_sections, do_summarize, max_attempts, compact,
                    placeholders, do_assemble, output, output_format):
    """直驱模式：引擎自己调本地/离线 LLM，跑完生成循环。无需 Agent 编排。

    每次 LLM 调用都是无状态单 prompt；中断后重跑本命令自动续传。
    遇到缺输入（feed_more）或连续失败会停下报告，不硬闯。
    """
    from paper_derived.runner import run_session
    from paper_derived.engine.session_engine import session_assemble
    from paper_derived.format_writer import write_document

    if compact:
        from paper_derived.engine._paths import set_compact
        set_compact(True)

    client = _make_client(api_base, model, api_key, temperature, max_output, timeout)

    def on_event(ev: dict) -> None:
        click.echo(json.dumps(ev, ensure_ascii=False))

    summary = run_session(
        session_id, client,
        window=window, max_sections=max_sections,
        do_summarize=do_summarize, max_attempts=max_attempts,
        placeholders=placeholders, on_event=on_event,
    )

    if summary["status"] == "ready_to_assemble" and do_assemble:
        from paper_derived.session_store import load_session as _load
        doc = session_assemble(session_id)
        sess, _, _ = _load(session_id)
        out_path = output or sess.output_path
        if out_path:
            written = write_document(doc, out_path, fmt=output_format or sess.output_format or None)
            click.echo(json.dumps({"event": "assembled", "output": str(written)}, ensure_ascii=False))
        else:
            click.echo(json.dumps({
                "event": "assembled",
                "hint": f"未指定输出路径。导出: session assemble -s {session_id} -O <file>",
            }, ensure_ascii=False))

    if summary["status"] in ("stuck",) or summary["failed"]:
        raise SystemExit(1)


@session.command("list")
def session_list_cmd():
    """列出所有会话。"""
    from paper_derived.session_store import list_sessions

    sessions = list_sessions()
    if not sessions:
        click.echo("(暂无会话)")
        return
    _output_json(sessions)


@session.command("delete")
@click.argument("session_id")
def session_delete_cmd(session_id):
    """删除会话。"""
    from paper_derived.session_store import delete_session

    delete_session(session_id)
    click.echo(f"会话 '{session_id}' 已删除")


# ── LLM 直驱命令 ────────────────────────────────────────────────


@main.group(name="llm")
def llm_group():
    """直驱模式：本地/离线 OpenAI 兼容 Provider 直接执行 prompt."""


@llm_group.command("config")
@click.option("--api-base", default=None, help="LLM 端点（远程 OpenAI 兼容地址 / claude-cli / cmd:…）")
@click.option("--model", "-m", default=None, help="模型名（须与 provider 的模型清单一致，如 ollama list 输出）")
@click.option("--api-key", default=None, help="API Key（不需要则不填）")
@click.option("--window", default=None, type=int, help="Provider 上下文窗口（tokens），直驱命令未指定 --window 时的默认值")
@click.option("--clear", is_flag=True, default=False, help="清除已保存的配置")
def llm_config_cmd(api_base, model, api_key, window, clear):
    """查看/保存 LLM Provider 持久化配置（~/.paper-derived/llm.json）。

    不带参数 = 查看当前配置；带参数 = 增量更新并保存。
    保存后所有直驱命令（session run / gen run / llm exec / register-auto）
    未显式给 --api-base 时自动使用该配置。
    """
    from paper_derived.llm import load_llm_config, save_llm_config, LLM_CONFIG_PATH, PROVIDER_GUIDE

    if clear:
        LLM_CONFIG_PATH.unlink(missing_ok=True)
        click.echo(json.dumps({"status": "cleared"}, ensure_ascii=False))
        return

    cfg = load_llm_config()
    updates = {k: v for k, v in
               [("api_base", api_base), ("model", model), ("api_key", api_key), ("window", window)]
               if v is not None}
    if updates:
        cfg.update(updates)
        save_llm_config(cfg)

    shown = dict(cfg)
    if shown.get("api_key"):
        shown["api_key"] = shown["api_key"][:4] + "****"
    if not cfg.get("api_base"):
        click.echo(PROVIDER_GUIDE)
        raise SystemExit(2)
    click.echo(json.dumps({"status": "saved" if updates else "current",
                           "config_file": str(LLM_CONFIG_PATH), **shown}, ensure_ascii=False))


@llm_group.command("test")
@_llm_client_options
def llm_test_cmd(api_base, model, api_key, temperature, max_output, timeout):
    """连通性测试：向 Provider 发一次最小调用，验证端点/模型/认证是否可用。"""
    import time as _time
    from paper_derived.llm import LLMError

    client = _make_client(api_base, model, api_key, temperature, max_output, timeout)
    t0 = _time.time()
    try:
        reply = client.chat("", "只回复两个字符：OK", max_tokens=8)
    except LLMError as e:
        click.echo(json.dumps({"status": "failed", "error": str(e)[:400]}, ensure_ascii=False))
        raise SystemExit(1)
    click.echo(json.dumps({
        "status": "ok",
        "latency_s": round(_time.time() - t0, 2),
        "reply_head": reply[:40],
        "client": type(client).__name__,
    }, ensure_ascii=False))


@llm_group.command("exec")
@click.argument("prompt_file", type=click.Path(exists=True))
@_llm_client_options
@click.option("--output", "-o", "response_file", required=True, type=click.Path(),
              help="LLM 响应写入该文件（之后照常用对应命令的 --parse 解析）")
def llm_exec_cmd(prompt_file, api_base, model, api_key, temperature, max_output, timeout,
                 response_file):
    """执行一个 `--out` 落盘的 prompt 文件，响应写入文件。

    离线环境下替代「子代理执行」：register / feed / extract / validate / revise
    等所有含 LLM 步骤都可用本命令执行，再用原命令 --parse 解析。
    """
    from paper_derived.llm import read_prompt_file, LLMError

    client = _make_client(api_base, model, api_key, temperature, max_output, timeout)
    system, user = read_prompt_file(prompt_file)
    try:
        response = client.chat(system, user)
    except LLMError as e:
        click.echo(json.dumps({"status": "error", "error": str(e)[:500]}, ensure_ascii=False))
        raise SystemExit(1)

    p = Path(response_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(response, encoding="utf-8")
    click.echo(json.dumps({
        "status": "executed",
        "prompt_file": str(prompt_file),
        "response_file": str(response_file),
        "response_chars": len(response),
    }, ensure_ascii=False))


# ── Helpers ────────────────────────────────────────────────────


def _load_session_or_error(session_id: str):
    """加载 session 对象, 用于 build_feed_prompt 等需要 session 对象的函数。"""
    from paper_derived.session_store import load_session
    session, _, _ = load_session(session_id)
    return session


if __name__ == "__main__":
    main()
