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


LLM_CONFIG_PATH = Path.home() / ".paper-derived" / "llm.json"

PROVIDER_GUIDE = """\
未配置 LLM Provider。直驱模式需要一个可用的 LLM 端点，请三选一：

  1) 持久化配置（推荐，一次配置全部直驱命令生效）：
     paper-derived llm config --api-base <端点> -m <模型名> [--api-key <key>] [--window <tokens>]
     然后 paper-derived llm test 验证连通。

  2) 环境变量：PAPER_DERIVED_API_BASE / PAPER_DERIVED_MODEL / PAPER_DERIVED_API_KEY

  3) 命令行参数：--api-base <端点> -m <模型名>

端点示例（生产环境通常是远程服务，不是本机）：
  https://llm.example.com/v1          远程 vLLM / 推理网关（OpenAI 兼容）
  http://10.0.0.8:11434/v1            局域网 Ollama 主机
  https://api.anthropic.com/v1        Anthropic（需 API key）
  claude-cli                          本机已登录的 claude CLI（无需 API）
  cmd:<agent命令>                     任意 agent CLI 的 headless 模式"""


def load_llm_config() -> dict:
    """读取持久化的 provider 配置（不存在返回空 dict）."""
    try:
        return json.loads(LLM_CONFIG_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_llm_config(cfg: dict) -> None:
    LLM_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LLM_CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


class ProviderNotConfigured(RuntimeError):
    """未配置 LLM Provider（附引导文案）。"""

    def __init__(self):
        super().__init__(PROVIDER_GUIDE)


class LLMError(RuntimeError):
    """LLM 调用失败（重试耗尽后抛出）。"""


class ClaudeCLIClient:
    """通过本机 `claude` CLI 的 headless 模式（claude -p）调用 LLM.

    适用场景：在 Claude Code 等 CLI Agent 环境内运行直驱命令
    （session run / gen run / llm exec），无需任何 API 地址或 key——
    子进程继承本机已登录的 claude 认证（订阅或 API 均可）。
    每次调用 = 一次无状态 headless 会话，与 OpenAI 客户端语义一致。
    """

    def __init__(
        self,
        model: str = "",
        temperature: float = 0.2,          # claude -p 不暴露温度，仅为接口兼容
        max_output_tokens: int = 4096,     # 同上
        timeout: float = 600.0,
        retries: int = 2,
        binary: str = "claude",
    ):
        self.model = model
        self.timeout = timeout
        self.retries = retries
        self.binary = binary

    def chat(self, system: str, user: str, max_tokens: int | None = None) -> str:
        """headless 调用，与 Agent 环境完全隔离：

        - --system-prompt **整体替换** Claude Code 的 Agent 系统提示
          （不是 append——否则引擎指令只是 Agent 人格后面的附注）
        - --exclude-dynamic-system-prompt-sections 去掉环境/git 等动态注入段
        - --setting-sources "" 不加载 user/project/local 任何设置
        - --strict-mcp-config（且不给 --mcp-config）不加载任何 MCP
        - --disallowedTools "*" + --max-turns 1 禁用工具、单轮作答
        - --no-session-persistence 不落 session 文件
        - 子进程 cwd 切到中立临时目录，避免项目 CLAUDE.md/skills 注入
        """
        import subprocess
        import tempfile

        cmd = [
            self.binary, "-p",
            "--output-format", "text",
            "--exclude-dynamic-system-prompt-sections",
            "--setting-sources", "",
            "--strict-mcp-config",
            "--disallowedTools", "*",
            "--max-turns", "1",
            "--no-session-persistence",
        ]
        if self.model:
            cmd += ["--model", self.model]
        cmd += ["--system-prompt", system or "你是文档生成助手，严格按用户消息中的要求输出，不输出任何多余内容。"]

        neutral_cwd = Path(tempfile.gettempdir()) / "pd-llm-neutral"
        neutral_cwd.mkdir(parents=True, exist_ok=True)

        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            if attempt > 0:
                time.sleep(2 ** attempt)
            try:
                proc = subprocess.run(
                    cmd, input=user, capture_output=True, text=True, errors="replace",
                    timeout=self.timeout, cwd=str(neutral_cwd),
                )
            except FileNotFoundError as e:
                raise LLMError(
                    f"找不到 `{self.binary}` 可执行文件——claude-cli provider 需要本机安装并登录 Claude Code"
                ) from e
            except subprocess.TimeoutExpired as e:
                last_err = LLMError(f"claude -p 执行超时（{self.timeout}s）")
                continue
            if proc.returncode != 0:
                last_err = LLMError(f"claude -p 退出码 {proc.returncode}: {proc.stderr.strip()[:300]}")
                continue
            out = proc.stdout.strip()
            if not out:
                last_err = LLMError("claude -p 返回空输出")
                continue
            return out
        raise last_err  # type: ignore[misc]


class CmdLLMClient:
    """通用 Agent CLI provider：任意有 headless 模式的 agent CLI 一行接入.

    api_base 形如 `cmd:<命令模板>`，借用该 CLI 已登录的 Provider 认证：

        cmd:opencode run                  # OpenCode（prompt 走 stdin）
        cmd:codex exec                    # Codex CLI
        cmd:gemini -p                     # Gemini CLI
        cmd:pi --print                    # Pi Agent（按其 headless 用法填）
        cmd:mytool --prompt-file {prompt_file}   # 需要文件入参的 CLI

    占位符（都可选）：
        {model}        → -m 传入的模型名
        {prompt_file}  → system+user 合并写入的临时文件路径
        {system_file}  → 仅 system 的临时文件路径
        {user_file}    → 仅 user 的临时文件路径
    无 *_file 占位符时，system+user 合并后从 stdin 送入。
    命令的 stdout 即响应。
    """

    def __init__(self, cmd_template: str, model: str = "",
                 timeout: float = 600.0, retries: int = 2):
        self.cmd_template = cmd_template.strip()
        self.model = model
        self.timeout = timeout
        self.retries = retries

    @staticmethod
    def _merge(system: str, user: str) -> str:
        if not system:
            return user
        return f"[系统指令，严格遵循]\n{system}\n\n[任务]\n{user}"

    def chat(self, system: str, user: str, max_tokens: int | None = None) -> str:
        import shlex
        import subprocess
        import tempfile

        tmpdir = Path(tempfile.mkdtemp(prefix="pd-cmd-"))
        files = {
            "{prompt_file}": tmpdir / "prompt.md",
            "{system_file}": tmpdir / "system.md",
            "{user_file}": tmpdir / "user.md",
        }
        template = self.cmd_template.replace("{model}", self.model)
        use_stdin = not any(ph in template for ph in files)
        if "{prompt_file}" in template:
            files["{prompt_file}"].write_text(self._merge(system, user), encoding="utf-8")
        if "{system_file}" in template:
            files["{system_file}"].write_text(system, encoding="utf-8")
        if "{user_file}" in template:
            files["{user_file}"].write_text(user, encoding="utf-8")
        for ph, path in files.items():
            template = template.replace(ph, str(path))
        cmd = shlex.split(template)
        stdin_text = self._merge(system, user) if use_stdin else None

        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            if attempt > 0:
                time.sleep(2 ** attempt)
            try:
                proc = subprocess.run(
                    cmd, input=stdin_text, capture_output=True, text=True, errors="replace",
                    timeout=self.timeout,
                )
            except FileNotFoundError as e:
                raise LLMError(f"找不到命令 `{cmd[0]}`（cmd: provider）") from e
            except subprocess.TimeoutExpired:
                last_err = LLMError(f"`{cmd[0]}` 执行超时（{self.timeout}s）")
                continue
            if proc.returncode != 0:
                last_err = LLMError(
                    f"`{cmd[0]}` 退出码 {proc.returncode}: {proc.stderr.strip()[:300]}")
                continue
            out = proc.stdout.strip()
            if not out:
                last_err = LLMError(f"`{cmd[0]}` 返回空输出")
                continue
            return out
        raise last_err  # type: ignore[misc]


def make_client(api_base: str, model: str, api_key: str = "", temperature: float = 0.2,
                max_output_tokens: int = 4096, timeout: float = 600.0):
    """按 api_base 选择客户端：

    - "claude-cli" → ClaudeCLIClient（本机已登录的 claude CLI，完全隔离的 headless）
    - "cmd:<命令模板>" → CmdLLMClient（任意 agent CLI 的 headless 模式，借用其认证）
    - 其他 → LLMClient（OpenAI 兼容 HTTP API；含 Anthropic 的 OpenAI 兼容端点
      https://api.anthropic.com/v1，需 API key）
    """
    cfg = load_llm_config()
    api_base = api_base or cfg.get("api_base", "")
    model = model or cfg.get("model", "")
    api_key = api_key or cfg.get("api_key", "")
    if not api_base:
        raise ProviderNotConfigured()

    base = api_base.strip()
    if base.lower() in ("claude-cli", "claude"):
        return ClaudeCLIClient(model=model, temperature=temperature,
                               max_output_tokens=max_output_tokens, timeout=timeout)
    if base.lower().startswith("cmd:"):
        return CmdLLMClient(base[4:], model=model, timeout=timeout)
    return LLMClient(api_base=api_base, model=model, api_key=api_key,
                     temperature=temperature, max_output_tokens=max_output_tokens,
                     timeout=timeout)


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
