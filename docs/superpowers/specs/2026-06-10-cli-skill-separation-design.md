# CLI / Skill 独立安装包设计

日期：2026-06-10

## 背景

paper-derived 项目当前将 CLI 和 Skill 捆绑在同一个 Python 包里。`derive install-skill` 命令仅将 SKILL.md 复制到 `~/.claude/skills/`。

问题：
1. **多 Agent 支持** — Skill 不只给 Claude Code，还要支持 OpenCode、Copilot 等
2. **离线安装** — 真实离线环境，需要 tar.gz + 纯 shell 安装
3. **Skill 不是 Python 包** — 它是给 Agent 读的指令文件集，不需要 Python 运行时

## 目标

- CLI 和 Skill 成为两个独立产品，平级存在于同一 repo
- CLI 以单二进制为主要分发形态（PyInstaller 打包），用户无需 Python/uv 环境
- Skill 通过 `install.sh --adapter <platform>` 安装到各 Agent 的 skill 目录，纯文件复制
- 两个产品完全解耦，可独立演进

## 目录结构

```
paper-derived/                          # git repo
├── cli/                                # CLI 产品根目录
│   └── paper_derived/                  # Python 包（import 名不变）
│       ├── __init__.py
│       ├── cli.py                      # 删除 install-skill 命令
│       ├── llm.py
│       ├── storage.py
│       ├── engine/
│       │   ├── _paths.py              # 新增：PROMPTS_DIR 兼容打包模式
│       │   ├── template.py
│       │   ├── input_asset.py
│       │   ├── generator.py
│       │   ├── validator.py
│       │   └── doc_ops.py
│       ├── models/
│       ├── prompts/                    # 7 个 .md 文件
│       └── mcp/
│
├── skill/                              # Skill 产品根目录
│   ├── SKILL.md                        # 通用编排手册
│   ├── references/                     # 参考文档
│   │   ├── commands.md                 # derive CLI 命令参考
│   │   └── data-models.md             # 数据模型参考
│   ├── examples/                       # 示例
│   │   └── api-design-workflow.md      # 完整工作流示例
│   └── install.sh                      # 安装脚本（--adapter 参数）
│
├── scripts/
│   └── build-cli.sh                    # PyInstaller 构建脚本
│
├── build/                              # 编译产物（gitignore）
│   ├── paper-derived-0.1.0-darwin-arm64
│   ├── paper-derived-0.1.0-darwin-x86_64
│   ├── paper-derived-0.1.0-linux-arm64
│   └── paper-derived-0.1.0-linux-x86_64
│
├── tests/                              # 测试（import 路径不变）
├── pyproject.toml                      # CLI 包配置
├── README.md
└── README.zh-CN.md
```

## 变更清单

### 1. 代码搬迁

将 `paper_derived/` 目录整体移至 `cli/paper_derived/`。

```bash
mkdir -p cli
mv paper_derived cli/paper_derived
```

### 2. 新增 `engine/_paths.py`

5 个 engine 文件当前各自定义 `PROMPTS_DIR = Path(__file__).parent.parent / "prompts"`，不兼容 PyInstaller 打包模式。抽取为统一模块：

- 新增 `cli/paper_derived/engine/_paths.py`，提供 `get_prompts_dir()` 兼容开发模式和 `_MEIPASS` 模式
- `template.py`、`input_asset.py`、`generator.py`、`validator.py`、`doc_ops.py` 改为 `from paper_derived.engine._paths import PROMPTS_DIR`

### 3. `pyproject.toml` 修改

```toml
[tool.setuptools.packages.find]
where = ["cli"]
include = ["paper_derived", "paper_derived.*"]

[tool.setuptools.package-data]
paper_derived = ["prompts/*.md"]
# 删除 "skill/SKILL.md" — Skill 不再是 Python 包的一部分

[project.scripts]
# 入口命令从 derive 改为 paper-derived
paper-derived = "paper_derived.cli:main"
```

### 4. 删除 `install-skill` 命令

从 `cli/paper_derived/cli.py` 中删除 `install-skill` 命令（约 L317-331）。Skill 安装改由 `skill/install.sh` 负责。

### 5. 新增 `skill/` 目录

从 `cli/paper_derived/skill/` 移出 `SKILL.md` 到 `skill/SKILL.md`，并新增：

- `skill/references/commands.md` — derive CLI 命令参考
- `skill/references/data-models.md` — 数据模型参考
- `skill/examples/api-design-workflow.md` — 完整工作流示例
- `skill/install.sh` — 安装脚本

### 6. `install.sh` 实现

```bash
#!/usr/bin/env bash
# paper-derived-skill 安装脚本
# 用法: ./install.sh --adapter claude [--project-dir ./path]

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

### 7. 新增 `scripts/build-cli.sh`

PyInstaller 构建脚本，支持多平台编译。每个平台生成独立的二进制文件。

产物命名规则：`paper-derived-{version}-{os}-{arch}`

```
build/
├── paper-derived-0.1.0-darwin-arm64
├── paper-derived-0.1.0-darwin-x86_64
├── paper-derived-0.1.0-linux-arm64
└── paper-derived-0.1.0-linux-x86_64
```

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

> **跨平台编译**：PyInstaller 不支持交叉编译，每个平台需要在本平台构建。推荐用 GitHub Actions 多 runner 矩阵：
> ```yaml
> strategy:
>   matrix:
>     include:
>       - os: macos-14    # arm64
>       - os: macos-13    # x86_64
>       - os: ubuntu-22.04  # x86_64
>       - os: ubuntu-22.04  # arm64 via QEMU
> ```

### 8. 更新 README 项目结构树

英文和中文 README 中的项目结构树更新为：

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
└── install.sh              # 安装脚本
```

### 9. 更新 `skill/SKILL.md`

- 删除对 `derive install-skill` 的引用（命令已删除）
- 新增 `install.sh` 安装说明
- L175 `paper_derived/prompts/` 路径引用保留不改（这是安装后的包内路径）

### 10. 重建开发环境

```bash
rm -rf paper_derived.egg-info .venv
uv sync
```

## CLI 单二进制打包

CLI 的主要分发形态是单二进制文件，用户无需安装 Python 或 uv。

### 打包要点

| 项 | 说明 |
|----|------|
| 入口 | `cli/paper_derived/cli.py` |
| 依赖 | 仅 `click>=8.0`，二进制体积很小 |
| 数据文件 | `prompts/*.md` 通过 `--add-data` 打入二进制 |
| 输出 | `build/paper-derived-{version}-{os}-{arch}`（单文件，约 5-8MB） |
| `PROMPTS_DIR` | PyInstaller 打包后 `Path(__file__)` 不可用，需改用 `sys._MEIPASS` 或 `importlib.resources` 定位 prompts |

### `PROMPTS_DIR` 适配

PyInstaller 打包后，运行时文件在临时目录 `_MEIPASS` 下。当前 5 个 engine 文件都使用 `Path(__file__).parent.parent / "prompts"`，需改为兼容开发模式和打包模式：

```python
# cli/paper_derived/engine/_paths.py（新增）
import sys
from pathlib import Path

def get_prompts_dir() -> Path:
    """定位 prompts 目录，兼容开发模式和 PyInstaller 打包模式。"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包模式
        return Path(sys._MEIPASS) / "paper_derived" / "prompts"
    # 开发模式
    return Path(__file__).parent.parent / "prompts"

PROMPTS_DIR = get_prompts_dir()
```

5 个 engine 文件改为 `from paper_derived.engine._paths import PROMPTS_DIR`。

### 开发模式仍可用

二进制是主要分发形态，但开发时仍用 `uv sync` + `uv run paper-derived`。pyproject.toml 保持不变，不强制 PyInstaller。

## 不变的部分

- 所有 `from paper_derived.*` import 语句 — 包名不变
- `storage.py` 的 `TEMPLATES_DIR` — 用户主目录路径
- 所有测试文件 — 使用包导入，无硬编码路径

## 变更的部分（补充）

- 入口命令从 `derive` 改为 `paper-derived`，入口点 `paper_derived.cli:main` 不变

## 安装方式汇总

| 产品 | 安装方式 |
|------|---------|
| CLI | 下载 `paper-derived-{version}-{os}-{arch}` 二进制 → 重命名为 `paper-derived` 并加入 PATH |
| CLI（开发） | `uv sync` → `uv run paper-derived` |
| Skill（Claude Code） | `./install.sh --adapter claude` |
| Skill（Copilot） | `./install.sh --adapter copilot --project-dir ./my-project` |
| Skill（OpenCode） | `./install.sh --adapter opencode`（输出配置路径） |