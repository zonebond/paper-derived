# 任务：资料体检——评估输入是否足以填充模板各 Section

规则：
1. 你只评估资料充足度，不决定 Section 取舍（所有 Section 最终都会生成，缺资料的用 placeholder）。
2. `input_dependent` 的 Section：对照输入摘要与实体判断，给 ok | warning | critical；critical 必须在 hint 说明缺什么。
3. `self_contained` 的 Section 一律 ok。

只输出以下 JSON，无任何其他文字：

```json
{
  "ok": true,
  "summary": "5/6 Section 资料充足，1 个缺资料",
  "sections": [
    {
      "section_id": "section-id",
      "section_title": "标题",
      "status": "ok | warning | critical",
      "hint": "若不足，说明缺什么"
    }
  ]
}
```

## 模板信息
