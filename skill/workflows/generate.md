# 工作流一：生成文档（主路径）

这是最高频的路径。用户给输入资料，指定文档类型，你要编排全流程。

> **大文档（15+ Section、多份输入、需断点续传）推荐使用 [Session-Driven 生成](session.md)。**

## 🔴 核心原则一：结构完整性优先

**输出文档必须包含模板定义的全部 Section，一个都不能少。**

- 资料充足 → Section 有完整内容，`status: "generated"`
- 资料不足 → Section 保留骨架，`status: "placeholder"`，`hints` 说明缺什么
- **绝对禁止**因资料不足而 skip/omit 任何 Section；章节编号、标题层级、嵌套关系始终完整保留

引擎层有结构完整性守卫（缺失 Section 自动补 placeholder），但最好让 LLM 一开始就输出完整结构。

## 🔴 核心原则二：上下文纪律（防 token 爆炸）

本工作流每一步都是「引擎构造 prompt → LLM 执行 → 引擎解析」。**执行 prompt 的 LLM 必须是子代理，不是你（主编排上下文）。** 违反此原则，几份大资料 + 一次整档生成就能撑爆上下文。规则：

1. **主 Agent 绝不亲自执行引擎输出的 prompt**——用 Task 工具起子代理（权限给 Read/Write/Bash）。
2. **prompt 用 `--out` 落盘到 `.pd/prompts/`**；子代理把响应写入 `.pd/responses/`；主 Agent 只对响应文件 `--parse` 并读**状态**。解析产物大的命令（`input register`、`gen extract`、`gen generate`）一律加 `-O <file>` 落盘。
3. **主 Agent 绝不读取 prompt 文件、响应文件、输入资产原文的正文内容。**

### 子代理执行协议（本文件通用，凡「执行 prompt」处均套用）

```bash
$PAPER_DERIVED_BIN <cmd> <args> --out .pd/prompts/<key>.md       # ① 落盘 prompt（文本格式）
# ② 起子代理：读 .pd/prompts/<key>.md（==== SYSTEM ==== 之后是系统指令，==== USER ==== 之后是任务），
#    严格按其要求生成，把完整响应写入 .pd/responses/<key>.json（遵守 SKILL.md「响应写盘纪律」：
#    已存在先 rm -f；超长响应先 Write 首段再 Bash 逐段追加），只回 DONE <key>，不输出正文到对话
$PAPER_DERIVED_BIN <cmd> <args> --parse .pd/responses/<key>.json # ③ 主 Agent 只看返回状态
```

> 尤其注意 `gen generate` 全量模式：整档 DocumentTree 响应极易超过子代理单条回复的输出上限，一次 Write 必被截断（`InputValidationError: content missing`）。要么让子代理分段追加写入，要么直接改用下方「分批生成」把单次响应做小——**大模板优先选分批**。

准备工作目录：`mkdir -p .pd/prompts .pd/responses .pd/assets`

## Step 0: 识别意图

从用户请求提取：**目标文档类型**、**输入资料**（文件/粘贴文本/引用）、**特殊要求**。

## Step 1: 确认模板

```bash
$PAPER_DERIVED_BIN template list --json
```

已有对应模板 → 直接用。没有 → 告诉用户「需要先注册一个 XX 类型的模板，请给我一份满意的样例文档」→ 跳到 register.md。

## Step 2: 注册输入资产（走子代理）

对每份资料，套用子代理协议。**这一步含原始资料原文，是主上下文的头号爆点，务必下放子代理：**

```bash
# ① 落盘注册 prompt
$PAPER_DERIVED_BIN input register <file> -n <name> --out .pd/prompts/reg-<name>.md
# ② 子代理读 .pd/prompts/reg-<name>.md 执行 → 写 .pd/responses/reg-<name>.json → DONE
# ③ 解析并落盘 InputAsset（-O 必加：stdout 只回状态摘要，资产 JSON 不进主上下文）
$PAPER_DERIVED_BIN input register <file> -n <name> --parse .pd/responses/reg-<name>.json --slim -O .pd/assets/input-<name>.json
# → {"status":"asset_written","asset_file":".pd/assets/input-<name>.json","entities":42,...}
```

产物：包含 `summary` + `entities` 的 InputAsset JSON 文件（`.pd/assets/input-<name>.json`）。所有输入注册完得到一个 JSON 文件列表（主 Agent 只需记住路径，不读内容）。

> 用户直接贴文本（无文件路径）时，先写入临时文件，再走同样流程。

### 大文档分块注册（并行子代理）

超大文档（超上下文窗口）用 `--chunk-size` 指定分块：

```bash
$PAPER_DERIVED_BIN input register <file> -n <name> --chunk-size 30000 --out .pd/prompts/reg-<name>.md
```

`--out` 模式下引擎**自动把每块写成独立文件** `.pd/prompts/reg-<name>.chunk-<i>.md`，stdout 只回：
`{"status":"prompts_written","mode":"chunked","total_chunks":4,"prompt_files":[...],"total_prompt_tokens":...}`。

**编排（关键：每块一个子代理，可并行）：**
1. 主 Agent 只看 stdout 摘要里的 `prompt_files` 列表，**不读任何分块文件的内容**（每块含 30000 字符原文）。
2. **并发**起 N 个子代理，第 i 个读 `.pd/prompts/reg-<name>.chunk-<i>.md` 执行 → 写 `.pd/responses/reg-<name>-chunk-<i>.json` → DONE。
3. 合并（`--slim` 省略 raw_content；`-O` 落盘，主上下文只收状态摘要）：

```bash
$PAPER_DERIVED_BIN input register <file> -n <name> \
  --parse-chunks .pd/responses/reg-<name>-chunk-0.json \
  --parse-chunks .pd/responses/reg-<name>-chunk-1.json \
  --parse-chunks .pd/responses/reg-<name>-chunk-2.json --slim -O .pd/assets/input-<name>.json
```

合并策略：summary 分号拼接；entities 按 `(kind,name)` 去重保留最详版本；raw_content 保留完整原文（但 `--slim` 会在产出 JSON 里置空）。

### `--slim`（大文档必用）

大文档的 `raw_content` 会让 InputAsset JSON 达数百 KB，读取即撑爆上下文。`--slim` 效果：产出 JSON 的 `raw_content` 置空（数百 KB → 几 KB），`metadata.source` 保留原路径可回查，下游命令基于 `summary`+`entities` 生成不依赖原文（引擎在 `raw_content` 超 20000 字符时自动省略原文）。

**推荐：大文档（>30000 字符）始终 `--chunk-size` + `--slim`，且注册全程走子代理。**

## Step 3: 资料体检（走子代理）

```bash
$PAPER_DERIVED_BIN gen preflight -i .pd/assets/input-1.json -i .pd/assets/input-2.json -t <template-id> --out .pd/prompts/preflight.md
# → 子代理执行 → .pd/responses/preflight.json
$PAPER_DERIVED_BIN gen preflight -i .pd/assets/input-1.json -i .pd/assets/input-2.json -t <template-id> --parse .pd/responses/preflight.json
```

**决策**：全 `ok` → 继续；有 `warning` → 告知用户可能影响质量，让其决定；有 `critical` → 必须告知并等补充。

## Step 4: 实体抽取（走子代理，可选但推荐）

```bash
$PAPER_DERIVED_BIN gen extract -i .pd/assets/input-1.json -i .pd/assets/input-2.json -t <template-id> --out .pd/prompts/extract.md
# → 子代理执行 → .pd/responses/extract.json
$PAPER_DERIVED_BIN gen extract -i .pd/assets/input-1.json -i .pd/assets/input-2.json -t <template-id> --parse .pd/responses/extract.json -O .pd/extract-result.json
```

向用户展示**摘要**（如「识别到 X 个接口、Y 个字段、Z 个认证方案」）。用户可确认或修正；有修正则保存为 `--overrides` 传给 Step 5。

## Step 5: 生成文档（走子代理）

```bash
$PAPER_DERIVED_BIN gen generate -i .pd/assets/input-1.json -i .pd/assets/input-2.json -t <template-id> --out .pd/prompts/gen.md
# → 子代理读 .pd/prompts/gen.md 执行 → 写 .pd/responses/gen.json → DONE
$PAPER_DERIVED_BIN gen generate -i .pd/assets/input-1.json -i .pd/assets/input-2.json -t <template-id> --parse .pd/responses/gen.json -O .pd/output.json
# 有 Step 4 修正时追加：--overrides corrected-extract.json
```

得到 DocumentTree 存 `.pd/output.json`（主 Agent 不读其正文，只看 `--parse` 状态）。

### 大模板分批生成（Section > 20，如 SRS 38 节）

一次性生成会让单个 prompt 过大（即使在子代理里也吃力）。改用**分批**，每批一个子代理：

1. **生成大纲**（确定性，无需 LLM/子代理）：
   ```bash
   $PAPER_DERIVED_BIN gen outline -t <template-id> -O .pd/doc.json
   ```
2. **实体抽取**（走子代理，见 Step 4），保存 `.pd/extract-result.json`。
3. **分批填充**：每批 4–8 个 Section，`--sections` 选章、`--extract` 选相关实体、`--into` 合并回主文档。**批次间必须串行**（都读写 `.pd/doc.json`，并行会互相覆盖）：
   ```bash
   # 批次 1
   $PAPER_DERIVED_BIN gen generate -i .pd/assets/input-1.json -i .pd/assets/input-2.json -t <template-id> \
     --sections scope,identification,referenced-documents \
     --extract .pd/extract-result.json --into .pd/doc.json --out .pd/prompts/batch-1.md
   # → 子代理执行 .pd/prompts/batch-1.md → .pd/responses/batch-1.json → DONE
   $PAPER_DERIVED_BIN gen generate -i .pd/assets/input-1.json -i .pd/assets/input-2.json -t <template-id> \
     --sections scope,identification,referenced-documents \
     --extract .pd/extract-result.json --into .pd/doc.json -O .pd/doc.json --parse .pd/responses/batch-1.json
   # 批次 2、3… 重复，串行
   ```

**优势**：每批 prompt 仅含目标 Section 模板指令 + 关联实体（50KB+ → 1–3KB），风格/校验指令完整保留跨批一致，非目标 Section 不被覆盖。

**SRS 38 节分批建议：**
| 批次 | Section | 数量 |
|------|---------|------|
| 1 | scope, identification, csci-overview, document-overview, referenced-documents | 5 |
| 2 | states-and-modes, capability-requirements | 2+ |
| 3 | external-interface-requirements, interface-identification, interface-details, internal-interface-requirements, internal-data-requirements | 5 |
| 4 | adaptability, security, safety, environment, quality-characteristics, reliability, maintainability | 7 |
| 5 | computer-resource-requirements, hardware-requirements, hardware-resource-usage, software, communication | 5 |
| 6 | design-constraints, personnel, training, support, packaging, other, priority | 7 |
| 7 | qualification-provisions, test-plan, test-methods, traceability, notes, appendices | 6 |

> Section 更多、依赖更复杂时，直接改用 [session.md]，它把分批/上下文/续传都托管了。

## Step 6: 质检（走子代理）

```bash
$PAPER_DERIVED_BIN gen validate .pd/output.json -t <template-id> --out .pd/prompts/validate.md
# → 子代理执行 → .pd/responses/validate.json
$PAPER_DERIVED_BIN gen validate .pd/output.json -t <template-id> --parse .pd/responses/validate.json
```

**决策**：
- `passed = true` → 交付
- `CRITICAL` + `fixable` → 自动 revise 修复（**修复循环也走子代理**，见 revise.md，最多 3 次）
- `CRITICAL` + `input_dependent` → 告知用户需确认或补充

## Step 7: 交付

文档树在 `.pd/output.json`。把 Markdown 渲染给用户预览，并说明：各 Section 状态（generated/placeholder）、需注意的 hints、可随时要求局部或全局修改。
