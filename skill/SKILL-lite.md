---
name: paper-derived
description: 从模板和输入资料生成结构化文档（直驱精简版）。当用户请求生成设计文档、注册文档模板、把资料整理成格式文档时使用。
version: 0.2.0
---

# Paper Derived · Lite（小模型 Agent 前台版）

> **Skill 版本：v0.2.0-lite** <!-- BUILD_INFO -->

你是**前台**：听懂用户要什么 → 发**一条**命令 → 把结果讲给用户。
全部重活（结构、生成、重试、占位、审计）由引擎直驱完成，你不做任何多步编排。

```bash
PAPER_DERIVED_BIN="./paper-derived"   # 相对本 skill 目录
```

## 三条禁令

1. 禁止读取 `.pd/` 下任何文件的正文，禁止把大段生成内容复述进对话。
2. 禁止自行编排多步流程（不派子代理、不手动 feed/prompt/parse）——只用下面三条命令。
3. 报错时把命令的 stdout 原文给用户看，不要自己猜原因。

## 0. Provider（本会话第一次用前先查）

```bash
$PAPER_DERIVED_BIN llm config
```

退出码 2 = 未配置 → 按它输出的引导**向用户收集**：端点地址、模型名、是否要 key、窗口大小。然后：

```bash
$PAPER_DERIVED_BIN llm config --api-base <端点> -m <模型> [--api-key <key>] --window <tokens>
$PAPER_DERIVED_BIN llm test
```

## 1. 注册模板（用户给了样例文档）

```bash
$PAPER_DERIVED_BIN template register-auto <样例文件> -n <模板名> --window <tokens> --compact --progress
```

## 2. 生成文档（用户给了输入资料）

```bash
$PAPER_DERIVED_BIN template list                     # 找 template-id
$PAPER_DERIVED_BIN gen run -t <template-id> -i <资料1> [-i <资料2>…] \
  --window <tokens> --compact --progress -O <交付文件.md>
```

中断或失败：**原样重跑同一条命令**即断点续传。

## 3. 汇报

把 `--progress` 输出的**最后几行**转述给用户（完成统计、审计结果、占位节清单、交付文件路径）。
交付文件在当前目录；过程文件在 `.pd/`，可提示用户确认交付后删除。
