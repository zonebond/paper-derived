# CLI / Skill 独立安装包分离 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 paper-derived 的 CLI 和 Skill 拆分为两个独立产品，CLI 支持单二进制分发，Skill 支持多 Agent 平台安装。

**Architecture:** CLI 代码从 `paper_derived/` 搬迁到 `cli/paper_derived/`，Skill 从包内移到独立 `skill/` 目录。engine 模块抽取 `_paths.py` 统一 PROMPTS_DIR 兼容 PyInstaller 打包。CLI 入口命令从 `derive` 改为 `paper-derived`。

**Tech Stack:** Python 3.10+, Click, PyInstaller, Bash

---

## 文件变更地图

| 操作 | 文件路径 | 职责 |
|------|---------|------|
| 创建 | `cli/paper_derived/engine/_paths.py` | PROMPTS_DIR 兼容打包模式 |
| 创建 | `skill/SKILL.md` | 从包内移出的编排手册 |
| 创建 | `skill/references/commands.md` | CLI 命令参考 |
| 创建 | `skill/references/data-models.md` | 数据模型参考 |
| 创建 | `skill/examples/api-design-workflow.md` | 完整工作流示例 |
| 创建 | `skill/install.sh` | 多平台安装脚本 |
| 创建 | `scripts/build-cli.sh` | PyInstaller 构建脚本 |
| 移动 | `paper_derived/` → `cli/paper_derived/` | 整体搬迁 |
| 移动 | `paper_derived/skill/SKILL.md` → `skill/SKILL.md` | Skill 独立 |
| 修改 | `pyproject.toml` | 包发现路径、入口命令、package-data |
| 修改 | `cli/paper_derived/engine/template.py` | 改用 `_paths.PROMPTS_DIR` |
| 修改 | `cli/paper_derived/engine/input_asset.py` | 同上 |
| 修改 | `cli/paper_derived/engine/generator.py` | 同上 |
| 修改 | `cli/paper_derived/engine/validator.py` | 同上 |
| 修改 | `cli/paper_derived/engine/doc_ops.py` | 同上 |
| 修改 | `cli/paper_derived/cli.py` | 删除 `install-skill` 命令 |
| 修改 | `skill/SKILL.md` | 更新安装说明和命令名 |
| 修改 | `README.md` | 更新项目结构树和安装说明 |
| 修改 | `README.zh-CN.md` | 同上 |
| 修改 | `.gitignore` | 新增 `build/` 目录 |
| 删除 | `cli/paper_derived/skill/` 目录 | 已移到独立 `skill/` |

---

### Task 1: 搬迁代码目录

将 `paper_derived/` 整体移至 `cli/paper_derived/`。

**Files:**
- Move: `paper_derived/` → `cli/paper_derived/`

- [ ] **Step 1: 创建目标目录并移动代码**

```bash
cd /Users/zonebondx/workspace/prototypes/paper-derived
mkdir -p cli
mv paper_derived cli/paper_derived
```

- [ ] **Step 2: 验证移动成功**

```bash
ls cli/paper_derived/__init__.py cli/paper_derived/cli.py cli/paper_derived/engine/template.py
```

Expected: 三个文件都存在

- [ ] **Step 3: 提交搬迁**

```bash
git add -A
git commit -m "refactor: move paper_derived/ to cli/paper_derived/"
```

---

### Task 2: 修改 pyproject.toml

更新包发现路径、入口命令和 package-data。

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 更新 pyproject.toml**

将当前内容：

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "paper-derived"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "click>=8.0.0",
]

[project.scripts]
derive = "paper_derived.cli:main"

[tool.setuptools.packages.find]
include = ["paper_derived", "paper_derived.*"]

[tool.setuptools.package-data]
paper_derived = ["prompts/*.md", "skill/SKILL.md"]
```

替换为：

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "paper-derived"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "click>=8.0.0",
]

[project.scripts]
paper-derived = "paper_derived.cli:main"

[tool.setuptools.packages.find]
where = ["cli"]
include = ["paper_derived", "paper_derived.*"]

[tool.setuptools.package-data]
paper_derived = ["prompts/*.md"]
```

- [ ] **Step 2: 删除旧 egg-info 并重建开发环境**

```bash
rm -rf paper_derived.egg-info .venv uv.lock
uv sync
```

- [ ] **Step 3: 验证新入口命令可用**

```bash
uv run paper-derived --help
```

Expected: 显示帮助信息，命令名为 `paper-derived`

- [ ] **Step 4: 提交**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: update pyproject.toml — where=cli, entry=paper-derived, remove skill package-data"
```

---

### Task 3: 创建 engine/_paths.py 并更新 5 个 engine 文件

抽取统一的 PROMPTS_DIR 模块，兼容开发模式和 PyInstaller 打包模式。

**Files:**
- Create: `cli/paper_derived/engine/_paths.py`
- Modify: `cli/paper_derived/engine/template.py`
- Modify: `cli/paper_derived/engine/input_asset.py`
- Modify: `cli/paper_derived/engine/generator.py`
- Modify: `cli/paper_derived/engine/validator.py`
- Modify: `cli/paper_derived/engine/doc_ops.py`
- Test: `tests/test_engine.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_engine.py` 末尾添加：

```python
class TestPromptsDir:
    """测试 PROMPTS_DIR 在开发模式下正确定位。"""

    def test_prompts_dir_exists(self):
        from paper_derived.engine._paths import PROMPTS_DIR
        assert PROMPTS_DIR.exists(), f"PROMPTS_DIR 不存在: {PROMPTS_DIR}"

    def test_prompts_dir_has_seven_files(self):
        from paper_derived.engine._paths import PROMPTS_DIR
        md_files = list(PROMPTS_DIR.glob("*.md"))
        assert len(md_files) == 7, f"期望 7 个 .md 文件，找到 {len(md_files)}: {md_files}"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_engine.py::TestPromptsDir -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'paper_derived.engine._paths'`

- [ ] **Step 3: 创建 `_paths.py`**

创建 `cli/paper_derived/engine/_paths.py`：

```python
"""路径工具 — 定位 prompts 目录，兼容开发模式和 PyInstaller 打包模式."""

from __future__ import annotations

import sys
from pathlib import Path


def get_prompts_dir() -> Path:
    """定位 prompts 目录.

    开发模式下使用 __file__ 相对路径；
    PyInstaller 打包模式下使用 sys._MEIPASS。
    """
    if getattr(sys, "frozen", False):
        # PyInstaller 打包模式
        return Path(sys._MEIPASS) / "paper_derived" / "prompts"
    # 开发模式
    return Path(__file__).parent.parent / "prompts"


PROMPTS_DIR = get_prompts_dir()
```

- [ ] **Step 4: 更新 5 个 engine 文件**

每个文件做两处修改：(a) 删除 `from pathlib import Path`（如果只被 PROMPTS_DIR 使用）和 `PROMPTS_DIR = ...` 行；(b) 添加 `from paper_derived.engine._paths import PROMPTS_DIR`。

**`cli/paper_derived/engine/template.py`**（当前行 15-16）：

删除：
```python
from pathlib import Path
```
（保留其他导入）

删除：
```python
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
```

添加（在 `from paper_derived.storage import ...` 之后）：
```python
from paper_derived.engine._paths import PROMPTS_DIR
```

**`cli/paper_derived/engine/input_asset.py`**（当前行 6-10）：

删除：
```python
from pathlib import Path
```

删除：
```python
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
```

添加（在 `from paper_derived.models.input_asset import ...` 之后）：
```python
from paper_derived.engine._paths import PROMPTS_DIR
```

**`cli/paper_derived/engine/generator.py`**（当前行 8-15）：

删除：
```python
from pathlib import Path
```

删除：
```python
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
```

添加（在 `from paper_derived.storage import ...` 之后）：
```python
from paper_derived.engine._paths import PROMPTS_DIR
```

**`cli/paper_derived/engine/validator.py`**（当前行 5-12）：

删除：
```python
from pathlib import Path
```

删除：
```python
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
```

添加（在 `from paper_derived.storage import ...` 之后）：
```python
from paper_derived.engine._paths import PROMPTS_DIR
```

**`cli/paper_derived/engine/doc_ops.py`**（当前行 5-10）：

删除：
```python
from pathlib import Path
```

删除：
```python
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
```

添加（在 `from paper_derived.models.document import ...` 之后）：
```python
from paper_derived.engine._paths import PROMPTS_DIR
```

注意：如果 `Path` 在文件中还有其他用途（如 `template.py` 中 `Path` 用于参数类型），则只删除 `PROMPTS_DIR = ...` 行，保留 `from pathlib import Path`。

- [ ] **Step 5: 运行测试确认通过**

```bash
uv run pytest tests/test_engine.py -v
```

Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add cli/paper_derived/engine/_paths.py cli/paper_derived/engine/template.py cli/paper_derived/engine/input_asset.py cli/paper_derived/engine/generator.py cli/paper_derived/engine/validator.py cli/paper_derived/engine/doc_ops.py tests/test_engine.py
git commit -m "refactor: extract engine/_paths.py for PyInstaller-compatible PROMPTS_DIR"
```

---

### Task 4: 删除 install-skill 命令

从 CLI 中删除 `install-skill` 命令，Skill 安装改由 `skill/install.sh` 负责。

**Files:**
- Modify: `cli/paper_derived/cli.py`

- [ ] **Step 1: 删除 install-skill 命令**

在 `cli/paper_derived/cli.py` 中，删除第 317-331 行：

```python
@main.command("install-skill")
def install_skill():
    """安装 paper-derived skill 到 Claude Code."""
    import shutil
    skill_src = Path(__file__).parent / "skill" / "SKILL.md"
    if not skill_src.exists():
        click.echo(f"错误: skill 文件不存在 {skill_src}")
        raise SystemExit(1)
    dest_dir = Path.home() / ".claude" / "skills" / "paper-derived"
    dest_dir.mkdir(parents=True, exist_ok=True)
    skill_dest = dest_dir / "SKILL.md"
    if skill_dest.exists() or skill_dest.is_symlink():
        skill_dest.unlink()
    shutil.copy2(str(skill_src), str(skill_dest))
    click.echo(f"已安装 → {skill_dest}")
```

同时检查文件顶部是否有 `import shutil` 被此命令独占使用。如果 `shutil` 没有在其他地方使用，删除该导入。

- [ ] **Step 2: 验证命令已删除**

```bash
uv run paper-derived --help
```

Expected: 帮助信息中不再出现 `install-skill`

- [ ] **Step 3: 运行全部测试**

```bash
uv run pytest tests/ -v
```

Expected: 全部 PASS

- [ ] **Step 4: 提交**

```bash
git add cli/paper_derived/cli.py
git commit -m "feat: remove install-skill command from CLI"
```

---

### Task 5: 创建 Skill 独立目录

将 SKILL.md 从包内移出，创建 references/ 和 examples/ 目录。

**Files:**
- Move: `cli/paper_derived/skill/SKILL.md` → `skill/SKILL.md`
- Create: `skill/references/commands.md`
- Create: `skill/references/data-models.md`
- Create: `skill/examples/api-design-workflow.md`
- Create: `skill/install.sh`

- [ ] **Step 1: 移动 SKILL.md**

```bash
mkdir -p skill/references skill/examples
mv cli/paper_derived/skill/SKILL.md skill/SKILL.md
rmdir cli/paper_derived/skill
```

- [ ] **Step 2: 创建 `skill/references/commands.md`**

```markdown
# paper-derived CLI 命令参考

## 入口

```bash
paper-derived [COMMAND] [OPTIONS]
```

## 模板命令

### `paper-derived template register`

注册一个新模板。

```bash
paper-derived template register <sample-file> -n <name> [-d <description>]
```

- `<sample-file>`: 样例文档路径
- `-n, --name`: 模板 ID（必填）
- `-d, --description`: 模板描述

构造模式：输出 `{"system": "...", "user": "..."}` prompt JSON。

解析模式：加 `--parse <response-file>` 解析 LLM 响应，存储模板。

### `paper-derived template list`

列出所有已注册模板。

### `paper-derived template show`

显示模板详情。

```bash
paper-derived template show <template-id>
```

## 输入资产命令

### `paper-derived input register`

注册输入资产。

```bash
paper-derived input register <file> -n <name>
```

- `<file>`: 输入文件路径
- `-n, --name`: 资产名称

构造模式：输出 prompt JSON。
解析模式：加 `--parse <response-file>` 解析 LLM 响应。

## 生成命令

### `paper-derived gen preflight`

资料体检：检查输入是否覆盖模板各 Section 的依赖。

```bash
paper-derived gen preflight -i <input.json> ... -t <template-id>
```

### `paper-derived gen extract`

实体抽取：从输入中提取结构化字段。

```bash
paper-derived gen extract -i <input.json> ... -t <template-id>
```

### `paper-derived gen generate`

生成文档。

```bash
paper-derived gen generate -i <input.json> ... -t <template-id> [-O <output.json>] [--overrides <extract.json>]
```

### `paper-derived gen validate`

质检：校验生成的文档。

```bash
paper-derived gen validate <doc.json> -t <template-id>
```

## 修订命令

### `paper-derived revise section`

局部修改文档某个 Section。

```bash
paper-derived revise section <doc.json> <section-id> <instruction> [-O <output.json>]
```

### `paper-derived revise global`

全局修改文档。

```bash
paper-derived revise global <doc.json> <instruction> [-O <output.json>]
```

## 通用选项

- `--parse <response-file>`: 解析模式，解析 LLM 响应文件
- `--help`: 显示帮助信息
```

- [ ] **Step 3: 创建 `skill/references/data-models.md`**

```markdown
# paper-derived 数据模型参考

## Template

| 字段 | 类型 | 说明 |
|------|------|------|
| id | str | 模板唯一标识 |
| name | str | 模板显示名称 |
| description | str | 模板描述 |
| extraction_prompt | str | 抽取模块 prompt |
| structure_prompt | str | 结构模块 prompt |
| style_prompt | str | 风格模块 prompt |
| validation_prompt | str | 校验模块 prompt |
| section_ids | list[str] | Section ID 列表 |
| section_dependencies | dict | Section 依赖关系 |

## InputAsset

| 字段 | 类型 | 说明 |
|------|------|------|
| id | str | 资产唯一标识 |
| name | str | 资产名称 |
| type | str | 资产类型 |
| raw_content | str | 原始内容 |
| summary | str | AI 生成的摘要 |
| entities | list[Entity] | 提取的实体列表 |

## Entity

| 字段 | 类型 | 说明 |
|------|------|------|
| kind | str | 实体类型 |
| name | str | 实体名称 |
| description | str | 实体描述 |
| location | str | 在源文件中的位置 |

## DocumentTree

| 字段 | 类型 | 说明 |
|------|------|------|
| id | str | 文档 ID |
| title | str | 文档标题 |
| sections | list[Section] | 递归 Section 列表 |
| meta | DocumentMeta | 文档元数据 |

## Section

| 字段 | 类型 | 说明 |
|------|------|------|
| id | str | Section ID |
| title | str | Section 标题 |
| content | str | Markdown 内容 |
| children | list[Section] | 子 Section |
| level | int | 层级深度 |
| template_ref | str | 对应模板 Section ID |
| status | str | generated / placeholder |
| lineage | list[LineageRef] | 内容来源追溯 |
| hints | list[str] | 生成提示 |

## LineageRef

| 字段 | 类型 | 说明 |
|------|------|------|
| input_id | str | 来源输入资产 ID |
| section | str | 来源 Section |
| confidence | float | 置信度 |

## PreflightReport

| 字段 | 类型 | 说明 |
|------|------|------|
| ok | bool | 是否全部通过 |
| sections | list[SectionPreflight] | 各 Section 检查结果 |
| summary | str | 总结 |

## ValidationReport

| 字段 | 类型 | 说明 |
|------|------|------|
| passed | bool | 是否通过校验 |
| total_checkpoints | int | 总检查点数 |
| passed_count | int | 通过数 |
| failed_count | int | 失败数 |
| checkpoints | list[ValidationCheckpoint] | 检查点列表 |

## ValidationCheckpoint

| 字段 | 类型 | 说明 |
|------|------|------|
| rule | str | 校验规则描述 |
| severity | str | CRITICAL / WARNING |
| rule_type | str | fixable / input_dependent |
| passed | bool | 是否通过 |
| message | str | 详细信息 |
```

- [ ] **Step 4: 创建 `skill/examples/api-design-workflow.md`**

```markdown
# 示例：API 设计文档生成工作流

本示例展示如何用 paper-derived 从 API 规格资料生成一份 API 设计文档。

## 前提

- paper-derived CLI 已安装
- 已有 API 设计文档模板（如未注册，需先注册模板）

## 完整流程

### 1. 确认模板

```bash
paper-derived template list
```

如果列表中已有 `api-design` 模板，直接使用。否则需要先注册模板。

### 2. 注册输入资产

```bash
# 构造 prompt
paper-derived input register ./api-spec.md -n api-spec
# → 输出 prompt JSON，Agent 用 LLM 执行

# 解析 LLM 响应
paper-derived input register ./api-spec.md -n api-spec --parse /tmp/pd/input-api-spec.json
# → 输出 InputAsset JSON
```

### 3. 资料体检

```bash
paper-derived gen preflight -i input-api-spec.json -t api-design
# → 执行 prompt → 解析 → 得到 PreflightReport
```

检查结果：全部 ok → 继续；有 warning → 告知用户；有 critical → 等待补充。

### 4. 实体抽取

```bash
paper-derived gen extract -i input-api-spec.json -t api-design
# → 执行 prompt → 解析 → 得到 ExtractionResult
```

展示摘要：「从资料中识别到 12 个接口、45 个字段、3 个认证方案。」

### 5. 生成文档

```bash
paper-derived gen generate -i input-api-spec.json -t api-design -O output.json
# → 执行 prompt → 解析 → 得到 DocumentTree
```

### 6. 质检

```bash
paper-derived gen validate output.json -t api-design
# → 执行 prompt → 解析 → 得到 ValidationReport
```

如果通过 → 交付文档。如果有 CRITICAL fixable 问题 → 自动修订。

### 7. 交付

文档保存在 `output.json` 中，渲染 Markdown 内容给用户预览。
```

- [ ] **Step 5: 创建 `skill/install.sh`**

```bash
#!/usr/bin/env bash
# paper-derived-skill 安装脚本
# 用法: ./install.sh --adapter <claude|copilot|opencode> [--project-dir ./path]

set -euo pipefail

ADAPTER=""
PROJECT_DIR=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --adapter) ADAPTER="$2"; shift 2 ;;
    --project-dir) PROJECT_DIR="$2"; shift 2 ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done

if [[ -z "$ADAPTER" ]]; then
  echo "用法: ./install.sh --adapter <claude|copilot|opencode> [--project-dir ./path]"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

install_to() {
  local dest="$1"
  mkdir -p "$dest"
  cp "$SCRIPT_DIR/SKILL.md" "$dest/SKILL.md"
  if [[ -d "$SCRIPT_DIR/references" ]]; then
    cp -r "$SCRIPT_DIR/references" "$dest/references"
  fi
  if [[ -d "$SCRIPT_DIR/examples" ]]; then
    cp -r "$SCRIPT_DIR/examples" "$dest/examples"
  fi
  echo "已安装 → $dest"
}

case "$ADAPTER" in
  claude)
    if [[ -n "$PROJECT_DIR" ]]; then
      install_to "$PROJECT_DIR/.claude/skills/paper-derived"
    else
      install_to "$HOME/.claude/skills/paper-derived"
    fi
    ;;
  copilot)
    if [[ -n "$PROJECT_DIR" ]]; then
      install_to "$PROJECT_DIR/.github/skills/paper-derived"
    else
      install_to "$HOME/.copilot/skills/paper-derived"
    fi
    ;;
  opencode)
    echo "OpenCode 使用配置文件引用 skill，请将以下路径添加到 opencode.jsonc："
    echo "  { \"skills\": [\"$SCRIPT_DIR\"] }"
    ;;
  *)
    echo "不支持的 adapter: $ADAPTER（支持: claude, copilot, opencode）"
    exit 1
    ;;
esac
```

- [ ] **Step 6: 设置 install.sh 可执行权限**

```bash
chmod +x skill/install.sh
```

- [ ] **Step 7: 提交**

```bash
git add skill/
git commit -m "feat: create independent skill directory with references, examples, and install.sh"
```

---

### Task 6: 更新 SKILL.md

更新 Skill 编排手册：命令名从 `derive` 改为 `paper-derived`，删除 `install-skill` 引用，新增 `install.sh` 说明。

**Files:**
- Modify: `skill/SKILL.md`

- [ ] **Step 1: 更新 SKILL.md**

在 `skill/SKILL.md` 中做以下替换：

1. 将所有 `derive ` 替换为 `paper-derived `（注意保留空格，避免误替换 derive 在其他语境的出现）
2. 在文件末尾「参考」部分，删除 `可用命令：derive template|input|gen|revise --help`，替换为：

```
## 安装

```bash
# Claude Code（用户级）
./install.sh --adapter claude

# Claude Code（项目级）
./install.sh --adapter claude --project-dir ./my-project

# GitHub Copilot（项目级）
./install.sh --adapter copilot --project-dir ./my-project

# OpenCode（配置引用）
./install.sh --adapter opencode
```

## 参考

- 引擎 prompt 模板在 `paper_derived/prompts/` 目录
- 模板存储：`~/.paper-derived/templates/<id>/profile.json`
- 可用命令：`paper-derived template|input|gen|revise --help`
```

- [ ] **Step 2: 验证 SKILL.md 格式正确**

```bash
head -5 skill/SKILL.md
grep "paper-derived" skill/SKILL.md | head -3
grep "derive " skill/SKILL.md || echo "OK: no bare 'derive ' remaining"
```

Expected: SKILL.md 开头正常，有 `paper-derived` 命令，没有残留的 `derive ` 命令（只出现在 `paper-derived` 前缀的上下文中）

- [ ] **Step 3: 提交**

```bash
git add skill/SKILL.md
git commit -m "feat: update SKILL.md — rename derive to paper-derived, add install.sh docs"
```

---

### Task 7: 创建构建脚本和更新 .gitignore

**Files:**
- Create: `scripts/build-cli.sh`
- Modify: `.gitignore`

- [ ] **Step 1: 创建 `scripts/build-cli.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

VERSION=$(uv run python -c "import importlib.metadata; print(importlib.metadata.version('paper-derived'))" 2>/dev/null || echo "0.1.0")

OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
# 归一化架构名
case "$ARCH" in
  arm64|aarch64) ARCH="arm64" ;;
  x86_64|amd64)  ARCH="x86_64" ;;
esac

BINARY_NAME="paper-derived-${VERSION}-${OS}-${ARCH}"

echo "Building ${BINARY_NAME}..."

uv pip install pyinstaller
uv run pyinstaller \
  --name paper-derived \
  --onefile \
  --clean \
  --noconfirm \
  --distpath build \
  --workpath build/_work \
  --add-data "cli/paper_derived/prompts:paper_derived/prompts" \
  cli/paper_derived/cli.py

# 重命名为带平台后缀的文件
mv "build/paper-derived" "build/${BINARY_NAME}"

echo "Built: build/${BINARY_NAME}"
```

- [ ] **Step 2: 设置构建脚本可执行权限**

```bash
chmod +x scripts/build-cli.sh
```

- [ ] **Step 3: 更新 `.gitignore`**

在 `.gitignore` 末尾添加：

```
build/
```

- [ ] **Step 4: 提交**

```bash
git add scripts/build-cli.sh .gitignore
git commit -m "feat: add build-cli.sh for PyInstaller multi-platform builds"
```

---

### Task 8: 更新 README

更新英文和中文 README 的项目结构树和安装说明。

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`

- [ ] **Step 1: 更新 README.md**

替换项目结构部分：

旧内容：
```
paper_derived/
├── cli.py              # CLI entry point
├── llm.py              # JSON parsing only (no LLM calls)
├── storage.py          # Local file storage
├── engine/             # Engine: build_*_prompt() + parse_*_result()
├── models/             # Data models: Template, DocumentTree, InputAsset ...
├── prompts/            # 7 prompt templates (.md)
├── skill/              # Claude Code Skill
└── mcp/                # MCP Server (18 tools)
```

新内容：
```
cli/
└── paper_derived/
    ├── cli.py              # CLI entry point
    ├── llm.py              # JSON parsing only (no LLM calls)
    ├── storage.py          # Local file storage
    ├── engine/             # Engine: build_*_prompt() + parse_*_result()
    ├── models/             # Data models: Template, DocumentTree, InputAsset ...
    ├── prompts/            # 7 prompt templates (.md)
    └── mcp/                # MCP Server (18 tools)

skill/
├── SKILL.md                # Agent orchestration manual
├── references/             # Reference docs
├── examples/               # Workflow examples
└── install.sh              # Multi-platform install script

scripts/
└── build-cli.sh            # PyInstaller build script
```

更新安装说明：

旧内容：
```
## Install

```bash
git clone <this-repo>
cd paper-derived
uv sync
uv run derive --help
```

Install Agent skill for Claude Code:

```bash
uv run derive install-skill
```
```

新内容：
```
## Install

### CLI

```bash
git clone <this-repo>
cd paper-derived
uv sync
uv run paper-derived --help
```

Or download a pre-built binary from Releases.

### Agent Skill

```bash
cd paper-derived/skill
./install.sh --adapter claude          # Claude Code (user-level)
./install.sh --adapter claude --project-dir ./my-project  # project-level
./install.sh --adapter copilot --project-dir ./my-project  # GitHub Copilot
./install.sh --adapter opencode         # OpenCode
```
```

- [ ] **Step 2: 更新 README.zh-CN.md**

同样的替换，中文版：

项目结构部分替换为：

```
cli/
└── paper_derived/
    ├── cli.py              # CLI 入口
    ├── llm.py              # JSON 解析（不调 LLM）
    ├── storage.py           # 本地存储
    ├── engine/              # 引擎：build_*_prompt() + parse_*_result()
    ├── models/              # 数据模型：Template, DocumentTree, InputAsset ...
    ├── prompts/             # 7 个 prompt 模板 (.md)
    └── mcp/                 # MCP Server (18 tools)

skill/
├── SKILL.md                # Agent 编排手册
├── references/             # 参考文档
├── examples/               # 示例
└── install.sh              # 多平台安装脚本

scripts/
└── build-cli.sh            # PyInstaller 构建脚本
```

安装说明部分替换为：

```
## 安装

### CLI

```bash
git clone <this-repo>
cd paper-derived
uv sync
uv run paper-derived --help
```

或从 Releases 下载预编译二进制。

### Agent Skill

```bash
cd paper-derived/skill
./install.sh --adapter claude          # Claude Code（用户级）
./install.sh --adapter claude --project-dir ./my-project  # 项目级
./install.sh --adapter copilot --project-dir ./my-project  # GitHub Copilot
./install.sh --adapter opencode         # OpenCode
```
```

- [ ] **Step 3: 提交**

```bash
git add README.md README.zh-CN.md
git commit -m "docs: update README project structure and install instructions"
```

---

### Task 9: 端到端验证

验证所有变更正确工作。

- [ ] **Step 1: 运行全部测试**

```bash
uv run pytest tests/ -v
```

Expected: 全部 PASS

- [ ] **Step 2: 验证 CLI 命令**

```bash
uv run paper-derived --help
uv run paper-derived template list
```

Expected: 帮助信息正常，`install-skill` 不再出现

- [ ] **Step 3: 验证 Skill 安装脚本**

```bash
cd skill
./install.sh --adapter claude --project-dir /tmp/test-skill
ls /tmp/test-skill/.claude/skills/paper-derived/
```

Expected: 看到 `SKILL.md`、`references/`、`examples/`

- [ ] **Step 4: 验证构建脚本**

```bash
cd /Users/zonebondx/workspace/prototypes/paper-derived
./scripts/build-cli.sh
ls build/
```

Expected: 看到 `paper-derived-0.1.0-darwin-arm64`（或对应平台）

- [ ] **Step 5: 运行构建的二进制**

```bash
./build/paper-derived-0.1.0-darwin-arm64 --help
```

Expected: 显示帮助信息（如果平台不匹配则跳过此步）

- [ ] **Step 6: 清理构建产物**

```bash
rm -rf /tmp/test-skill
```