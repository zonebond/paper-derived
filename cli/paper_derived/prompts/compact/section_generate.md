# 任务：生成一个指定 Section

规则：
1. 资料充足 → `status: "generated"`，写完整内容；资料不足 → `status: "placeholder"`，写骨架说明并在 hints 标注缺什么。禁止空 content。
2. 严格使用提供的术语表和风格指南。
3. 不要编造实体列表中不存在的数据。
4. 引用其他章节用占位符 `{{ref:section-id}}`，禁止写死章节号。
5. 事实性内容标注 lineage。

只输出以下 JSON，无任何其他文字：

```json
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
```
