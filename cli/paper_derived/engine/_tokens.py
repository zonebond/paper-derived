"""Token 计数与预算管理 — 基于 tiktoken 的本地精确计数.

离线可用: tiktoken 的 encoding 数据打包在 PyInstaller 中。
降级: tiktoken 不可用时回退到字符估算。
"""

from __future__ import annotations

# 默认使用 cl100k_base (GPT-4 / Claude 通用)
_DEFAULT_ENCODING = "cl100k_base"

# 缓存 encoder 实例 (tiktoken 加载有 IO 开销)
_encoder = None


def _get_encoder():
    """获取 tiktoken encoder (惰性加载, 缓存)."""
    global _encoder
    if _encoder is not None:
        return _encoder
    try:
        import tiktoken
        _encoder = tiktoken.get_encoding(_DEFAULT_ENCODING)
        return _encoder
    except (ImportError, ValueError):
        # ImportError: tiktoken 未安装
        # ValueError: PyInstaller 构建中 tiktoken 找不到编码数据
        _encoder = None  # 明确标记不可用，避免反复尝试
        return None


def count_tokens(text: str, model: str = _DEFAULT_ENCODING) -> int:
    """精确计算 token 数.

    tiktoken 不可用时回退到字符估算:
      - CJK 字符: ~1.5 字符/token
      - 其他字符: ~4 字符/token
    """
    enc = _get_encoder()
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:
            pass  # 降级到字符估算

    # 降级: 字符估算
    cjk = sum(1 for c in text if "一" <= c <= "鿿")
    other = len(text) - cjk
    return int(cjk / 1.5 + other / 4)


def truncate_to_budget(
    text: str,
    budget: int,
    model: str = _DEFAULT_ENCODING,
) -> str:
    """截断文本到 token 预算内, 优先在段落边界截断.

    1. 先按段落 (\n\n) 尝试截断
    2. 超预算则按行截断
    3. 单行超预算则硬截断
    """
    if count_tokens(text, model) <= budget:
        return text

    # 按段落逐步累加
    paragraphs = text.split("\n\n")
    result_parts: list[str] = []
    used = 0
    for para in paragraphs:
        para_tokens = count_tokens(para, model)
        if used + para_tokens <= budget:
            result_parts.append(para)
            used += para_tokens
        else:
            # 段落内按行截断 — 保持段内单换行，重组后 append 为单个段落
            lines = para.split("\n")
            fitted_lines: list[str] = []
            for line in lines:
                line_tokens = count_tokens(line, model)
                if used + line_tokens <= budget:
                    fitted_lines.append(line)
                    used += line_tokens
                else:
                    # 单行硬截断
                    if used < budget:
                        remaining = budget - used
                        enc = _get_encoder()
                        if enc is not None:
                            tokens = enc.encode(line)
                            fitted_lines.append(enc.decode(tokens[:remaining]))
                        else:
                            # 字符估算截断
                            ratio = remaining / max(line_tokens, 1)
                            char_end = int(len(line) * ratio)
                            fitted_lines.append(line[:char_end])
                    break
            if fitted_lines:
                result_parts.append("\n".join(fitted_lines))  # 段内用单换行
            break

    return "\n\n".join(result_parts)
