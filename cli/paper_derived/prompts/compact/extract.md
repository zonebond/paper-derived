# 任务：按模板 Section 分组抽取结构化实体

规则：
1. sections 必须覆盖模板的**每一个** Section；资料不足的输出空 `found` 并在 hint 说明缺什么，禁止省略任何 Section。
2. 每项标注 kind、name、attributes、来源、confidence。
3. 不确定的内容给低 confidence，不要猜测。

只输出以下 JSON，无任何其他文字：

```json
{
  "summary": "从 N 份资料中识别到 X 个接口、Y 个字段…",
  "warnings": [],
  "sections": [
    {
      "section_id": "section-id",
      "section_title": "标题",
      "confidence": 0.8,
      "hint": "资料不足时说明",
      "found": [
        {
          "kind": "api_endpoint | field | table | rule | term | value",
          "name": "实体名称",
          "attributes": {"key": "value"},
          "source_input_id": "来源资产ID",
          "source_location": "来源位置",
          "confidence": 0.8
        }
      ]
    }
  ]
}
```

## 模板信息
