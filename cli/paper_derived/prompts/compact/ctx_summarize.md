# 任务：为 Section 生成压缩摘要

规则：
1. 2-4 句话、不超过 200 字，概括核心决策与结论。
2. 不含代码和详细参数。
3. key_entities 列 3-8 个最核心实体，格式 `kind:name`。

只输出以下 JSON，无任何其他文字：

```json
{
  "title": "Section 标题",
  "summary": "2-4 句压缩摘要。",
  "key_entities": ["kind:name"]
}
```
