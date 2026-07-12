# 任务：仅生成指定 Section 的部分文档树

规则（第 1 条为最高优先级）：
1. **只输出 `section_ids` 指定的 Section，且每一个都必须出现，禁止省略。** 资料充足 → `status: "generated"`；资料不足 → `status: "placeholder"` 写骨架说明并在 hints 标注缺什么。
2. 保持各目标 Section 的模板层级（level / children 子树）。
3. 遵循模板结构指令与风格指令，与已有文档风格一致。
4. 每个 Section 标注 lineage。
5. 输出前自检：指定的每个 Section ID 是否都在输出中。

只输出以下 JSON（只含本批 Section），无任何其他文字：

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
      "status": "generated | placeholder",
      "lineage": [
        {"input_id": "来源资产ID", "fragment_ref": "来源位置", "confidence": 0.8}
      ],
      "hints": []
    }
  ],
  "metadata": {
    "total_sections": 0,
    "generated_sections": 0,
    "placeholder_sections": 0
  }
}
```
