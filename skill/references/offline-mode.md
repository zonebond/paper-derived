# 离线 / 直驱模式（本地小模型 Provider）

当运行环境是离线的本地 LLM Provider（Ollama / vLLM / LM Studio / llama.cpp server 等，
OpenAI 兼容协议），且模型规模小、上下文窗口小时，**不要用 Agent 编排**——改用引擎直驱：

- `session run`：引擎自己调 Provider，跑完整个生成循环（next → prompt → 调用 → parse → summarize）。
  编排是确定性代码，零 LLM 参与；每次调用都是无状态单 prompt，不存在会爆的编排上下文。
- `llm exec`：执行任意 `--out` 落盘的 prompt 文件，替代「子代理执行」。
  register / feed / extract / validate / revise 等步骤全部靠它离线化。

## 全离线流水线示例

```bash
BIN=paper-derived
LLM="--api-base http://localhost:11434/v1 -m qwen2.5:14b"
export PAPER_DERIVED_COMPACT=1   # 小模型用精简版内置 prompt（见下）
mkdir -p .pd/prompts .pd/responses .pd/assets

# 1. 注册输入（小窗口 → chunk 收紧；见下方参数表）
$BIN input register spec.md -n spec --chunk-size 5000 --out .pd/prompts/reg.md
for f in .pd/prompts/reg.chunk-*.md; do
  i=$(basename $f .md); $BIN llm exec $f $LLM -o .pd/responses/$i.json
done
$BIN input register spec.md -n spec \
  $(for r in .pd/responses/reg.chunk-*.json; do echo --parse-chunks $r; done) \
  --slim -O .pd/assets/input-spec.json

# 2. 初始化 + 喂入
$BIN session init -t <template-id>          # 记录 $SID；budget 由 run --window 自动收缩
$BIN session feed -s $SID -i .pd/assets/input-spec.json --out .pd/prompts/feed.md
$BIN llm exec .pd/prompts/feed.md $LLM -o .pd/responses/feed.json
$BIN session feed -s $SID -i .pd/assets/input-spec.json --parse .pd/responses/feed.json

# 3. 直驱生成（全自动循环 + 自动组装）
$BIN session run -s $SID $LLM --window 32768 --compact -O output.md
```

中断后重跑同一条 `session run` 自动续传（checkpoint 在磁盘）。

## `session run` 行为要点

| 情况 | 行为 |
|------|------|
| `--window N` | 自动收缩预算：budget = min(现值, N/2)，一次生效并持久化 |
| 解析失败 | 自动追加格式修正指令重试（默认单节最多 3 次尝试） |
| 尝试耗尽 | 该节标记 failed，继续其余节；结束时汇总报告并以非零码退出 |
| `feed_more`（缺输入） | 停下报告缺哪些 Section，等人补料——不硬闯 |
| `--max-sections N` | 生成 N 节后停（人工分段审查的停点） |
| 上次中断残留的 generating | 自动重置为 ready 续跑 |
| 全部完成 | 默认自动 assemble；`-O` 或 init 时的 output_path 决定落盘位置 |

## 窗口参数表（中文 1 字 ≈ 1 token 估算）

| Provider 窗口 | `--window` | 派生 budget | `--chunk-size`（字符） | `--max-output` |
|---|---|---|---|---|
| 8K | 8192 | 4,096 | 2,500 | 2048 |
| 16K | 16384 | 8,192 | 5,000 | 3072 |
| 32K | 32768 | 16,384 | 12,000 | 4096 |
| 128K | 131072 | 60,000（默认档） | 30,000 | 4096 |

## Compact prompt（小模型必开）

引擎内置的 11 个系统 prompt 都有精简变体（`prompts/compact/`）：输出 JSON 契约与
标准版逐字一致（解析零影响），但剔除了全部解释性文字、反例和重复强调——这些内容
对大模型是保险，对小模型是纯窗口负担且稀释关键指令。

- `session run --compact`：直驱循环内的 section 生成与摘要用精简版
- `PAPER_DERIVED_COMPACT=1`：对所有构造 prompt 的命令生效（register / feed /
  extract / validate / revise 的 `--out` 步骤），离线流水线开头 export 一次即可
- compact 变体缺失的 prompt 自动回退标准版

## 小模型适配建议（窗口之外）

1. **温度调低**（默认 0.2 已偏保守），结构化输出更稳。
2. **摘要不要关**：`--no-summarize` 会让下游 prompt 越来越大，小窗口下必炸。
3. **质检与人审**：跑完后用 `session status` + `gen validate`（validate 的 prompt 用
   `llm exec` 执行）复核；小模型的 lineage 与事实性要重点抽查。
4. **模板 prompt 写短**：四个 prompt 模块中的长解释性文字对小模型是纯负担，
   注册模板时按"指令清单"风格写。
5. 连接参数可用环境变量固化：`PAPER_DERIVED_API_BASE` / `PAPER_DERIVED_MODEL` /
   `PAPER_DERIVED_API_KEY`。

## 与 Agent 编排的关系

在线有强模型（Claude Code 等）时照旧走 skill 的子代理协议——Agent 保有步骤间的
编辑判断力（补料决策、主动 revise、与用户交互）。离线小模型时用本模式，
把判断力还给人：`session run` 在关键节点停下，你审查后再继续。
