# 任务：对照模板校验指令，输出文档质检报告

规则（按优先级）：
1. **结构完整性最先查**：模板每个 Section ID 是否都在文档中？缺失 → `severity: CRITICAL`、`rule_type: fixable`。层级是否与模板一致？
2. placeholder Section 不算错误，但空 content 的 placeholder 算。
3. 逐项检查模板校验指令；每项标注 fixable（可修复）或 input_dependent（依赖输入资料）。
4. 其余维度：格式规范、术语一致性、数据完整性。

只输出以下 JSON，无任何其他文字：

```json
{
  "passed": true,
  "total_checkpoints": 10,
  "passed_count": 8,
  "failed_count": 2,
  "summary": "8/10 校验通过，2 个失败 (1 CRITICAL)",
  "checkpoints": [
    {
      "checkpoint": "校验项描述",
      "status": "PASSED | FAILED | WARNING",
      "section_id": "关联 Section ID，全局检查为空",
      "reason": "失败原因",
      "severity": "CRITICAL | WARNING",
      "rule_type": "fixable | input_dependent"
    }
  ]
}
```

## 模板校验指令
