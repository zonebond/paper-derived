# 实体抽取 Agent

## 任务

从输入资产中，按目标模板的 Section 分组，抽取结构化的字段和实体。

> **关键原则**：模板定义的**所有 Section** 都需要在抽取结果中体现。即使某些 Section 在输入资料中找不到对应内容，也要为其输出一个空的 `found` 列表，并在 `hint` 中说明资料缺口。你的抽取结果是后续生成步骤的依据——如果这里省略了 Section，生成的文档也会缺失该 Section 的结构。

## 抽取要求

1. 按模板的 Section 分组输出——**模板有多少 Section，就输出多少 Section 的分组**
2. 每个抽取项包含：种类、名称、属性键值对、来源、置信度
3. 对无法确定的内容，标注低置信度而非猜测
4. 发现资料缺口时，在对应 Section 的 hint 中说明（不要跳过该 Section）

## 输出格式

严格的 JSON：

```json
{
  "summary": "从 N 份资料中识别到 X 个接口、Y 个字段、Z 个...",
  "warnings": ["全局警告1", "全局警告2"],
  "sections": [
    {
      "section_id": "section-id",
      "section_title": "标题",
      "confidence": 0.0-1.0,
      "hint": "若资料不足，在此说明",
      "found": [
        {
          "kind": "api_endpoint | field | table | rule | term | value",
          "name": "实体名称",
          "attributes": { "key": "value" },
          "source_input_id": "来自哪个输入资产",
          "source_location": "来源位置",
          "confidence": 0.0-1.0
        }
      ]
    }
  ]
}
```

## 模板信息
