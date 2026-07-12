# 任务：分析原始资料，生成结构化 InputAsset

规则：
1. summary 一句话概括资料内容。
2. 抽取关键实体：接口、字段、数据表、术语、业务规则。
3. 每个实体标注 kind、name、description、location。

只输出以下 JSON，无任何其他文字：

```json
{
  "id": "输入资产 ID",
  "name": "资产名称",
  "type": "markdown | ddl | json_schema | pdf_text | plain_text",
  "summary": "一句话摘要",
  "entities": [
    {
      "kind": "api_endpoint | field | table | term | rule",
      "name": "实体名称",
      "description": "一句话描述",
      "location": "§章节名 或 段落位置"
    }
  ]
}
```

## 输入文本
