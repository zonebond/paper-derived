"""LLM 调用工具 — JSON 解析 + OpenAI 兼容客户端（直驱模式用）.

两种运行模式：
- Agent 驱动（默认）：引擎不调 LLM，只构造 prompt / 解析响应，由 Agent 负责执行。
- 直驱模式（离线/本地 Provider）：`LLMClient` 直接调 OpenAI 兼容 API
  （Ollama / vLLM / LM Studio / llama.cpp server 等），配合 `session run` /
  `llm exec` 命令，编排零 LLM 参与。
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

PROMPT_SYSTEM_MARKER = "==== SYSTEM ===="
PROMPT_USER_MARKER = "==== USER ===="


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


def read_prompt_file(path: str | Path) -> tuple[str, str]:
    """读取 `--out` 写出的文本 prompt 文件，返回 (system, user).

    文件格式（见 cli._write_prompt_text）：
        ==== SYSTEM ====
        <系统指令>

        ==== USER ====
        <任务>

    无标记时整个文件视为 user 消息。
    """
    text = Path(path).read_text(encoding="utf-8")
    if PROMPT_SYSTEM_MARKER not in text:
        return "", text.strip()
    body = text.split(PROMPT_SYSTEM_MARKER, 1)[1]
    if PROMPT_USER_MARKER in body:
        system, user = body.split(PROMPT_USER_MARKER, 1)
    else:
        system, user = body, ""
    return system.strip(), user.strip()


class LLMError(RuntimeError):
    """LLM 调用失败（重试耗尽后抛出）。"""


class LLMClient:
    """OpenAI 兼容 chat/completions 客户端（仅标准库，离线环境零依赖）.

    api_base 形如 http://localhost:11434/v1（Ollama）、http://localhost:8000/v1（vLLM）。
    """

    def __init__(
        self,
        api_base: str,
        model: str,
        api_key: str = "",
        temperature: float = 0.2,
        max_output_tokens: int = 4096,
        timeout: float = 600.0,
        retries: int = 2,
    ):
        self.api_base = api_base.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.timeout = timeout
        self.retries = retries

    def chat(self, system: str, user: str, max_tokens: int | None = None) -> str:
        """单轮调用，返回 assistant 文本。网络/5xx 错误按退避重试。"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": max_tokens or self.max_output_tokens,
            "stream": False,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{self.api_base}/chat/completions"
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            if attempt > 0:
                time.sleep(2 ** attempt)
            try:
                req = urllib.request.Request(url, data=body, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                if content is None:
                    raise LLMError(f"Provider 返回空 content: {json.dumps(data)[:300]}")
                return content
            except urllib.error.HTTPError as e:
                detail = ""
                try:
                    detail = e.read().decode("utf-8", errors="replace")[:300]
                except Exception:
                    pass
                # 4xx 是请求本身的问题（prompt 超窗、模型名错），重试无意义
                if 400 <= e.code < 500:
                    raise LLMError(f"HTTP {e.code} 来自 {url}: {detail}") from e
                last_err = LLMError(f"HTTP {e.code} 来自 {url}: {detail}")
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, KeyError, IndexError) as e:
                last_err = LLMError(f"调用 {url} 失败: {e!r}")

        raise last_err  # type: ignore[misc]
