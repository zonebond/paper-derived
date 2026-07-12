"""LLM 调用工具 — 已废弃，仅保留 JSON 解析工具。

引擎不调 LLM。LLM 调用由 Agent 工具 (Claude Code / OpenCode / Pi) 负责。
引擎只做：构造 prompt → 交给 Agent → Agent 调 LLM → 结果交给引擎解析。
"""

import json
import re


def extract_json(text: str) -> dict:
    """从 LLM 响应文本中提取 JSON 对象."""
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试提取 markdown code block 中的 JSON
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 尝试用大括号/方括号定位
    for pat in [r"\{[\s\S]*\}", r"\[[\s\S]*\]"]:
        m = re.search(pat, text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

    raise ValueError(f"无法从 LLM 响应中提取 JSON:\n{text[:500]}")
