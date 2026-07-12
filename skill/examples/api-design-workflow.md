# 示例：API 设计文档生成工作流

本示例展示如何用 paper-derived 从 API 规格资料生成一份 API 设计文档。

## 前提

- paper-derived CLI 已安装
- 已有 API 设计文档模板（如未注册，需先注册模板）

## 完整流程

### 1. 确认模板

```bash
paper-derived template list
```

如果列表中已有 `api-design` 模板，直接使用。否则需要先注册模板。

### 2. 注册输入资产

```bash
# 构造 prompt
paper-derived input register ./api-spec.md -n api-spec
# → 输出 prompt JSON，Agent 用 LLM 执行

# 解析 LLM 响应
paper-derived input register ./api-spec.md -n api-spec --parse /tmp/pd/input-api-spec.json
# → 输出 InputAsset JSON
```

### 3. 资料体检

```bash
paper-derived gen preflight -i input-api-spec.json -t api-design
# → 执行 prompt → 解析 → 得到 PreflightReport
```

检查结果：全部 ok → 继续；有 warning → 告知用户；有 critical → 等待补充。

### 4. 实体抽取

```bash
paper-derived gen extract -i input-api-spec.json -t api-design
# → 执行 prompt → 解析 → 得到 ExtractionResult
```

展示摘要：「从资料中识别到 12 个接口、45 个字段、3 个认证方案。」

### 5. 生成文档

```bash
paper-derived gen generate -i input-api-spec.json -t api-design -O output.json
# → 执行 prompt → 解析 → 得到 DocumentTree
```

### 6. 质检

```bash
paper-derived gen validate output.json -t api-design
# → 执行 prompt → 解析 → 得到 ValidationReport
```

如果通过 → 交付文档。如果有 CRITICAL fixable 问题 → 自动修订。

### 7. 交付

文档保存在 `output.json` 中，渲染 Markdown 内容给用户预览。