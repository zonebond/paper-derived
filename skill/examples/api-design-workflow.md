# 示例：API 设计文档生成工作流

本示例展示如何用 paper-derived 从 API 规格资料生成一份 API 设计文档。
**全程遵守上下文纪律**：prompt 落盘（`--out`）→ 子代理执行 → 响应落盘 → `--parse` 只看状态；大产物用 `-O` 落盘。

## 前提

- paper-derived CLI 已安装
- 已有 API 设计文档模板（如未注册，需先注册模板）

## 完整流程

### 0. 准备工作目录

```bash
mkdir -p .pd/prompts .pd/responses .pd/assets
```

### 1. 确认模板

```bash
paper-derived template list
```

如果列表中已有 `api-design` 模板，直接使用。否则需要先注册模板（见 workflows/register.md）。

### 2. 注册输入资产（走子代理）

```bash
# ① 落盘 prompt（文本格式，stdout 只回一行摘要）
paper-derived input register ./api-spec.md -n api-spec --out .pd/prompts/reg-api-spec.md
# → {"status":"prompt_written","prompt_file":".pd/prompts/reg-api-spec.md","prompt_tokens":8200}

# ② 起子代理：读 .pd/prompts/reg-api-spec.md（==== SYSTEM ==== / ==== USER ==== 两段），
#    严格按要求执行，把完整响应写入 .pd/responses/reg-api-spec.json，只回 DONE

# ③ 解析并落盘 InputAsset（主上下文只收状态摘要）
paper-derived input register ./api-spec.md -n api-spec \
  --parse .pd/responses/reg-api-spec.json --slim -O .pd/assets/input-api-spec.json
# → {"status":"asset_written","asset_file":".pd/assets/input-api-spec.json","entities":45,...}
```

### 3. 资料体检（走子代理）

```bash
paper-derived gen preflight -i .pd/assets/input-api-spec.json -t api-design --out .pd/prompts/preflight.md
# → 子代理执行 → .pd/responses/preflight.json → DONE
paper-derived gen preflight -i .pd/assets/input-api-spec.json -t api-design --parse .pd/responses/preflight.json
# → PreflightReport（状态报告，体积小）
```

检查结果：全部 ok → 继续；有 warning → 告知用户；有 critical → 等待补充。

### 4. 实体抽取（走子代理）

```bash
paper-derived gen extract -i .pd/assets/input-api-spec.json -t api-design --out .pd/prompts/extract.md
# → 子代理执行 → .pd/responses/extract.json → DONE
paper-derived gen extract -i .pd/assets/input-api-spec.json -t api-design \
  --parse .pd/responses/extract.json -O .pd/extract-result.json
# → {"status":"extract_written","output":".pd/extract-result.json","sections":8,"items":60,...}
```

展示摘要：「从资料中识别到 12 个接口、45 个字段、3 个认证方案。」

### 5. 生成文档（走子代理）

```bash
paper-derived gen generate -i .pd/assets/input-api-spec.json -t api-design --out .pd/prompts/gen.md
# → 子代理执行 → .pd/responses/gen.json → DONE
paper-derived gen generate -i .pd/assets/input-api-spec.json -t api-design \
  --parse .pd/responses/gen.json -O .pd/output.json
# → DocumentTree 存 output.json（主 Agent 不读其正文）
```

### 6. 质检（走子代理）

```bash
paper-derived gen validate .pd/output.json -t api-design --out .pd/prompts/validate.md
# → 子代理执行 → .pd/responses/validate.json → DONE
paper-derived gen validate .pd/output.json -t api-design --parse .pd/responses/validate.json
# → ValidationReport（状态报告）
```

如果通过 → 交付文档。如果有 CRITICAL fixable 问题 → 自动修订（走子代理，见 workflows/revise.md）。

### 7. 交付

文档树保存在 `.pd/output.json` 中，渲染 Markdown 内容给用户预览。
