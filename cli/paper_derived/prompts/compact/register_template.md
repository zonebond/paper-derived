# 任务：分析样例文档，生成四模块模板

从样例中学习：结构骨架（Section 与层级）、风格特征、每节的内容模式与输入依赖、隐含校验规则。

规则：
1. **样例中每个一级章节都必须出现在 sections 中，禁止遗漏**——包括文档末尾内容稀薄的章节（仅一句提示的「注释」、仅一张示例表的「附表」等），它们是独立章节不是附录尾巴。
2. 用户消息若含「结构预扫描锚点」清单，逐一覆盖每个锚点。
3. 输出前自检：样例编号标题 1…N 逐个有对应 Section。

只输出以下 JSON，无任何其他文字：

```json
{
  "id": "kebab-case-template-id",
  "name": "模板名称",
  "description": "一句话描述",
  "sections": [
    {
      "id": "parent-section",
      "title": "父级 Section 标题",
      "level": 1,
      "children": [
        {
          "id": "child-section",
          "title": "子级 Section 标题",
          "level": 2,
          "children": [],
          "dependency": {
            "type": "input_dependent",
            "description": "依赖什么类型的输入",
            "expected_sources": ["markdown", "ddl"]
          }
        }
      ],
      "dependency": {
        "type": "input_dependent | self_contained",
        "description": "依赖什么类型的输入",
        "expected_sources": ["markdown", "ddl"]
      }
    }
  ],
  "extraction_prompt": "【抽取指令】按 Section 说明：从哪类输入查找、匹配什么特征、如何格式化。按 Section 分组输出。",
  "structure_prompt": "【结构指令】列出全部 Section 的树形结构（id、title、level）。",
  "style_prompt": "【风格指令】术语使用、叙述语气、表格/列表习惯、代码块语言偏好。",
  "validation_prompt": "【校验指令】逐项检查清单；每项标注 fixable 或 input_dependent。"
}
```

## 输入样例文档
