# 任务：按模板生成完整文档树 (DocumentTree)

规则（第 1 条为最高优先级）：
1. **模板 `section_ids` 中的每一个 Section 都必须出现在输出中，禁止省略。** 资料充足 → `status: "generated"` 写完整内容；资料不足 → `status: "placeholder"` 写骨架说明并在 hints 标注缺什么。
2. 保持模板定义的层级（level / children）。
3. 遵循模板的结构指令与风格指令。
4. 每个 Section 标注 lineage。
5. 输出前自检：模板每个 Section ID 是否都在输出中。

只输出以下 JSON，无任何其他文字：

```json
{
  "document_id": "doc_xxx",
  "template_id": "模板ID",
  "input_ids": ["输入资产ID"],
  "title": "文档标题",
  "generated_at": "ISO时间戳",
  "sections": [
    {
      "id": "section-id (来自模板)",
      "title": "Section 标题",
      "content": "Markdown 正文",
      "children": [],
      "level": 1,
      "template_ref": "模板ID.section-id",
      "status": "generated | placeholder | empty",
      "lineage": [
        {"input_id": "来源资产ID", "fragment_ref": "来源位置", "confidence": 0.8}
      ],
      "hints": []
    }
  ],
  "metadata": {
    "model": "模型名",
    "total_sections": 0,
    "generated_sections": 0,
    "placeholder_sections": 0
  }
}
```

## 模板
