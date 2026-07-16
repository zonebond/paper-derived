---
name: paper-derived
description: 从样例模板和输入资料派生结构化开发文档。支持模板注册、文档生成/修改、Session-Driven 大文档生成、离线直驱模式。当用户请求生成设计文档、整理资料为格式文档、注册模板或修改文档章节时使用。
version: 0.2.0
---

# Paper Derived

> **Skill 版本：v0.2.0** <!-- BUILD_INFO -->
> 本会话首次触发本 skill 时，向用户报告一行版本信息：上面的 skill 版本 + `$PAPER_DERIVED_BIN version` 的输出（含 CLI 版本与构建 commit）。两者版本号不一致说明二进制与 skill 文档不同步，提示用户重新运行 install.sh。

从样例模板和输入资料派生结构化开发文档。

## 触发条件

当用户请求以下任意一项时触发本 skill：
- 「生成一份 XX 设计文档」
- 「把这些资料整理成 XX 格式的文档」
- 「给我一份样例文档，帮我注册成模板」
- 「修改这份文档的某个章节」
- 任何涉及从输入素材生成结构化文档的请求

## 你的角色

你是**编排者**。paper-derived 引擎是你的工具——它**不调 LLM**，只负责构造 prompt 和解析结果。

关键：引擎构造的 prompt 需要一个 LLM 去执行，但**执行者不应是你（主编排上下文）**。凡是需要执行 prompt 来生成/抽取内容的地方，都通过 **Task 工具下放给子代理**执行；你只负责发命令、落盘 prompt、收状态、做决策。理由见下方「上下文纪律」。

## 引擎路径

```bash
PAPER_DERIVED_BIN="./paper-derived"
```

> 路径相对于 skill 目录 `paper-derived/skill/`。通过 `cd $(dirname $PAPER_DERIVED_BIN)` 切换后执行。

每条命令的通用模式：

```bash
$PAPER_DERIVED_BIN <command> <args>                 # 构造 prompt（全量打 stdout，禁止在编排中使用）
$PAPER_DERIVED_BIN <command> <args> --out p.md       # 构造 prompt 并写入文本文件（必用，避免灌主上下文）
$PAPER_DERIVED_BIN <command> <args> --parse r.json   # 解析子代理产出的响应
```

`--out` 写出的是**纯文本文件**（不是 JSON）：`==== SYSTEM ====` 之后是系统指令，`==== USER ====` 之后是任务。真实换行、无超长单行，子代理用 Read 工具可完整读取。stdout 只回一行摘要（含 `prompt_tokens` 估算）。

## 🔴 上下文纪律（全流程铁律，防 token 爆炸）

本 skill 的每个流程本质是「引擎构造 prompt → 某个 LLM 执行 → 引擎解析」。爆上下文的唯一根源，是让**主编排上下文**去执行那些体积巨大的 prompt（受 `--budget` 约束可达数万 token）+ 承接生成结果，跨十几个 Section 累加必然超限，且 auto-compact 会摘丢跨节精确状态。因此：

1. **主 Agent 绝不亲自执行引擎输出的 prompt。** 一律用 Task 工具起子代理执行（工具权限给 Read/Write/Bash——Bash 用于分段追加写响应文件，见下方「响应写盘纪律」）。
2. **prompt 与响应一律走文件。** 用 `--out` 把 prompt 写入 `.pd/prompts/`；子代理把响应写入 `.pd/responses/`；主 Agent 只对 `.pd/responses/*.json` 跑 `--parse` 并读取其**状态**。解析产物大的命令（`input register`、`gen extract`、`gen generate`）一律加 `-O <file>` 落盘，stdout 只回状态摘要。
3. **主 Agent 绝不读取 `.pd/prompts/*`、`.pd/responses/*`、输入资产原文的正文内容。** 需要排查时，派子代理去读并回报要点。
4. **中间状态全部落盘**（ContextStore、checkpoint、.pd/prompts/responses），不驻留在你的对话里。这样即使 `/clear` 也能凭 `session_id` 续传。

### 子代理执行协议（通用）

对任何构造 prompt 的命令：

```bash
$PAPER_DERIVED_BIN <cmd> <args> --out .pd/prompts/<key>.md       # ① 落盘 prompt（文本格式）
# ② 起子代理，指令：读 .pd/prompts/<key>.md（==== SYSTEM ==== 之后是系统指令，==== USER ==== 之后是任务），
#    严格按其要求生成，把完整响应写入 .pd/responses/<key>.json（遵守下方响应写盘纪律），
#    只回 DONE <key>，不输出正文到对话
$PAPER_DERIVED_BIN <cmd> <args> --parse .pd/responses/<key>.json # ③ 主 Agent 只看返回状态
```

### 子代理响应写盘纪律（防单次 Write 截断）

子代理单条回复的输出 token 有上限。一次 Write 塞入超长全文，工具调用参数会在中途被截断成非法调用——表现为 `InputValidationError: file_path/content is missing` 反复失败。派发子代理时，把以下纪律写进它的指令：

1. **写前清场**：目标 `.pd/responses/<key>.json` 若已存在（上次残留的半截文件），先 `rm -f` 再写——Write 不允许覆盖未读过的已有文件。
2. **分段写入**：响应内容较长（超过约 1 万字）时，禁止一次 Write 全文。先用 Write 写入首段建立文件，剩余部分用 Bash 分多次追加，每次一段：
   ```bash
   cat >> .pd/responses/<key>.json <<'PD_EOF'
   <下一段内容>
   PD_EOF
   ```
3. **写完自检**：追加完成后用 `wc -c .pd/responses/<key>.json` 或读取尾部确认文件完整（结尾闭合），再回 DONE。

## 子代理失败/超时的恢复原则

子代理执行失败（超时、无响应、结果残缺）时，**恢复动作只有一种：把任务拆小后重派**。

1. **feed 超大** → 改为增量喂入：每次 `session feed` 只喂**一份**输入资产（可多次），
   单个 prompt 立刻缩小数倍；见 session.md Step 3。
2. **单节生成超大** → 调低 `session init --budget` 或改分批生成。
3. **注册资料超大** → `--chunk-size` 分块，每块一个子代理。
4. 重派时在子代理指令中注明：prompt 文件较大，分段 Read（offset/limit）读完整再执行。

**绝对禁止**向用户索要 LLM API 地址——在 Claude Code 环境内直驱**不需要任何 API**：
`--api-base claude-cli` 让引擎通过本机已登录的 `claude` CLI（headless 模式）直接调用 LLM。

拆小重派 2 轮仍失败、或任务量大（如 42 节模板逐节生成）想省编排开销时，
可**征得用户同意后**切换直驱（无需用户提供任何配置）：

```bash
$PAPER_DERIVED_BIN session run -s $SID --api-base claude-cli -m sonnet -O output.md
# 或一条龙：$PAPER_DERIVED_BIN gen run -t <tid> -i <资料>... --api-base claude-cli -m sonnet -O output.md
```

事件以 JSON 行输出到 stdout，主上下文只承载这些状态行——上下文纪律天然满足。
OpenAI 兼容 Provider（Ollama 等）的离线直驱见 references/offline-mode.md。

## 工作目录与交付物纪律

**所有过程文件进 `.pd/`（隐藏目录），用户的当前目录只留最终交付物。**

```
.pd/                     ← 过程文件，全部可随时删除
├── prompts/             ← --out 落盘的 prompt
├── responses/           ← 子代理写的 LLM 响应
├── assets/              ← input register 产出的 InputAsset JSON
├── extract-result.json  ← 抽取结果
├── doc.json             ← 分批生成的中间文档树
└── output.json          ← DocumentTree（渲染前的中间产物）

output.md / output.docx  ← 最终交付物：写在用户当前目录（或用户指定路径）
```

规则：
1. 开工先 `mkdir -p .pd/prompts .pd/responses .pd/assets`；一切 `--out` / `-O` 的中间产物路径都以 `.pd/` 开头。
2. **最终交付物（渲染出的 md/docx/pdf）是唯一写在 `.pd/` 之外的文件**，路径用用户指定的，未指定则放当前目录根。
3. 交付时告诉用户：过程文件在 `.pd/`，确认交付物无误后可整目录删除（`rm -rf .pd`）；如需断点续传或复查 lineage，暂留。
4. 若项目在 git 仓库中，建议提示用户把 `.pd/` 加入 `.gitignore`。

## 引擎路径下的命令

所有命令使用 `$PAPER_DERIVED_BIN`。命令清单见 `references/commands.md`。

## 工作流路由

> **离线/本地小模型场景**：用户明确要在离线 LLM Provider（Ollama/vLLM 等）下运行时，
> 不走下方 Agent 编排工作流——改用引擎直驱模式（`session run` + `llm exec`），
> 读取 `references/offline-mode.md` 按其流水线执行。

根据用户请求，**读取**对应工作流文件后再执行：

```
用户请求类型？
  │
  ├── 注册模板 → workflows/register.md
  ├── 修改已有文档 → workflows/revise.md
  │
  └── 生成文档 → 评估以下条件：
        │
        ├── Section 数 > 15？
        ├── 输入资料 > 3 份 或 单份 > 30K 字符？
        ├── 用户提到"暂停/继续/分步"？
        ├── 模板有 section_dependencies？
        │
        ├── 任一为是 → workflows/session.md（Session-Driven 生成）
        └── 全部为否 → workflows/generate.md（常规生成）
```

> **必须先读取工作流文件再执行。**

## 通用约束

1. **你必须让 prompt 被完整执行，但执行者是子代理，不是你。** 见上「上下文纪律」。
2. **每个 Section 的 lineage 必须真实。** 内容来自哪份输入资产的哪个部分，要标注清楚。
3. **质检失败时区分规则类型。** fixable → 自动修（修复循环也走子代理）；input_dependent → 问用户。
4. **结构完整性铁律。** 输出文档必须包含模板定义的全部 Section——资料不足时以 `placeholder` 保留骨架和标题，绝对禁止 skip/omit 任何 Section。

## Session 模式行为约束

使用 Session-Driven 生成时（workflows/session.md），额外遵守：

- **你是纯编排者，不是生成器。** 每个 Section 的 prompt 由子代理执行，你只发命令、落盘 prompt、收 DONE、`--parse` 看状态。
- **不要手动管理上下文。** `session prompt` 自动组装上下文，你不决定哪些 entity 进 prompt，也不读 prompt 内容。
- **prompt 走 `--out`，响应走 `.pd/responses/`。** 绝不让 `session prompt/feed/summarize` 的大 prompt 打进主上下文（用 `--out` 或 `> file`）。
- **不要写死章节号。** 用 `{{ref:section-id}}` 占位符，`session assemble` 自动替换。
- **不要绕过 session 命令直接操作原始文件。** 禁止 `cat`/`grep` 输入资产原文拼上下文——这些重活封装在 CLI 内部；需查数据用 `session search`。
- **每个 Section 生成后默认执行 summarize（走子代理）。** 摘要存入 ContextStore，让后续每个 Section 的 prompt 用摘要代替前序整节原文，控制下游 prompt 体积。
- **input register / gen validate 等含大 prompt 的步骤同样走子代理**，不要因为它们「不在循环里」就在主上下文执行。

## 参考文件（按需读取）

| 文件 | 内容 | 何时读取 |
|------|------|----------|
| `references/commands.md` | 全部 CLI 命令速查（含 `--out` 用法） | 忘了命令用法时 |
| `references/data-models.md` | 数据模型字段定义 | 需要理解返回值结构时 |
| `references/session-states.md` | Session 状态机 + 错误恢复 + 预算调优 | Session 遇到错误或需调优时 |
| `references/large-doc-strategies.md` | 大文档策略对比（分块/分批/Session） | 拿不准该用哪种策略时 |
| `references/offline-mode.md` | 离线/本地小模型直驱模式（`session run` / `llm exec`） | 用户要求在离线 LLM Provider 下运行时 |
| `examples/api-design-workflow.md` | API 设计文档生成示例 | 首次使用时参考 |

## 安装

```bash
./scripts/build-cli.sh                                    # 先构建二进制
./skill/install.sh --adapter claude                       # Claude Code（用户级）
./skill/install.sh --adapter claude --project-dir ./my-project   # 项目级
./skill/install.sh --adapter copilot --project-dir ./my-project  # GitHub Copilot
./skill/install.sh --adapter opencode                     # OpenCode
```
