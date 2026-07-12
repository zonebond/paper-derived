# paper-derived CLI 命令参考

## 入口

```bash
paper-derived [COMMAND] [OPTIONS]
```

通用模式：
```bash
paper-derived <command> <args>           # 构造 prompt → 输出 {"system": "...", "user": "..."}
paper-derived <command> <args> --parse response.json  # 解析 LLM 响应
```

## 模板命令

### `paper-derived template register`

注册一个新模板。

```bash
paper-derived template register <sample-file> -n <name> [-d <description>]
```

- `<sample-file>`: 样例文档路径
- `-n, --name`: 模板 ID（必填）
- `-d, --description`: 模板描述

构造模式：输出 `{"system": "...", "user": "..."}` prompt JSON。
解析模式：加 `--parse <response-file>` 解析 LLM 响应，存储模板。

### `paper-derived template list`

列出所有已注册模板。

### `paper-derived template show`

显示模板详情。

```bash
paper-derived template show <template-id>
```

### `paper-derived template delete`

删除模板。

```bash
paper-derived template delete <template-id>
```

## 输入资产命令

### `paper-derived input register`

注册输入资产。

```bash
paper-derived input register <file> -n <name> [--chunk-size 30000] [--slim]
```

- `<file>`: 输入文件路径
- `-n, --name`: 资产名称
- `--chunk-size`: 分块大小（字符数），0=不分块
- `--parse-chunks`: 合并分块结果（可多次指定）
- `--slim`: 精简模式，不存储 raw_content

构造模式：输出 prompt JSON。
解析模式：加 `--parse <response-file>` 解析 LLM 响应。

## 生成命令

### `paper-derived gen preflight`

资料体检：检查输入是否覆盖模板各 Section 的依赖。

```bash
paper-derived gen preflight -i <input.json> ... -t <template-id>
```

### `paper-derived gen extract`

实体抽取：从输入中提取结构化字段。

```bash
paper-derived gen extract -i <input.json> ... -t <template-id>
```

### `paper-derived gen outline`

生成文档大纲（骨架）。

```bash
paper-derived gen outline -t <template-id> [-O <output>] [-f json|md|docx|pdf]
```

### `paper-derived gen generate`

生成文档。

```bash
paper-derived gen generate -i <input.json> ... -t <template-id> [-O <output.json>]
  [--overrides <extract.json>]
  [--sections <id1,id2,...>] [--extract <extract.json>] [--into <doc.json>]
```

- `--sections`: 分批生成时指定目标 Section
- `--extract`: 抽取结果 JSON，用于筛选实体
- `--into`: 已有文档树路径，分批生成时合并

### `paper-derived gen validate`

质检：校验生成的文档。

```bash
paper-derived gen validate <doc.json> -t <template-id>
```

## 修订命令

### `paper-derived revise section`

局部修改文档某个 Section。

```bash
paper-derived revise section <doc.json> <section-id> <instruction> [-O <output.json>]
```

### `paper-derived revise global`

全局修改文档。

```bash
paper-derived revise global <doc.json> <instruction> [-O <output.json>]
```

## Session 命令

### `paper-derived session init`

初始化生成会话。无需 LLM。

```bash
paper-derived session init -t <template-id> [--budget 120000] [-O <output>] [-f <format>]
```

### `paper-derived session feed`

喂入输入资产，填充上下文库。

```bash
paper-derived session feed -s <session-id> -i <input.json> [-i <input2.json> ...] [--parse <response>]
```

### `paper-derived session next`

查询下一步操作。无需 LLM。

```bash
paper-derived session next -s <session-id>
```

返回：`generate` + section_id/batch | `assemble` | `feed_more` | `wait`

### `paper-derived session prompt`

获取 Section 生成 prompt（CLI 自动组装上下文）。

```bash
paper-derived session prompt -s <session-id> --section <section-id> [--parse <response>]
```

### `paper-derived session summarize`

生成 Section 摘要（存入 ContextStore，Agent 不可见）。

```bash
paper-derived session summarize -s <session-id> --section <section-id> [--parse <response>]
```

### `paper-derived session assemble`

组装最终文档（解析交叉引用，无需 LLM）。

```bash
paper-derived session assemble -s <session-id> [-O <output>] [-f md|docx|pdf|json]
```

### `paper-derived session status`

查看会话状态。无需 LLM。

```bash
paper-derived session status -s <session-id>
```

### `paper-derived session search`

搜索上下文库（带 token 预算防护）。无需 LLM。

```bash
paper-derived session search -s <session-id> <query> [--focus <entity_key>] [--budget 2000]
```

- `<query>`: 搜索关键词
- `--focus`: 聚焦到指定 entity_key，获取完整详情 + 原文片段
- `--budget`: 返回结果的 token 预算上限（默认 2000）

返回匹配的实体列表（snippet + confidence + score）。超出预算自动截断，用 `--focus` 下钻。

### `paper-derived session list`

列出所有会话。

### `paper-derived session delete`

删除会话。

```bash
paper-derived session delete <session-id>
```

## 通用选项

- `--parse <response-file>`: 解析模式，解析 LLM 响应文件
- `--help`: 显示帮助信息
