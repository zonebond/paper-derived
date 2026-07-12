# 任务：分析输入资产，按模板 Section 结构化抽取

规则：
1. sections 必须覆盖模板的**每一个** Section；资料不足的输出 `entity_keys: []` 并在 hint 说明缺什么，禁止省略任何 Section。
2. 每个实体标注 kind、name、来源、置信度、related_sections。
3. 不确定的内容给低 confidence，不要猜测。
4. 对高价值实体输出 fragments 原文片段（每段 ≤500 字）。
5. `entity_keys` 格式为 `kind:name`，与 entities 一致。

只输出以下 JSON，无任何其他文字：

```json
{
  "entities": [
    {
      "kind": "api_endpoint | field | table | rule | term | value",
      "name": "实体名称",
      "description": "一句话描述",
      "attributes": {"key": "value"},
      "source_input_id": "来源资产ID",
      "source_location": "来源位置",
      "confidence": 0.8,
      "related_sections": ["section-id"]
    }
  ],
  "sections": [
    {
      "section_id": "section-id",
      "section_title": "标题",
      "entity_keys": ["kind:name"],
      "confidence": 0.8,
      "hint": "资料不足时说明"
    }
  ],
  "fragments": [
    {"entity_key": "kind:name", "text": "关键原文片段"}
  ]
}
```
