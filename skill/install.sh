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
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 查找二进制文件：优先项目 build/ 目录，其次 skill 目录本身
find_binary() {
  # 1. 项目 build/ 目录中按版本+平台命名的二进制
  local binary
  binary="$(find "$PROJECT_ROOT/build" -name 'paper-derived-*' -type f -perm +111 2>/dev/null | head -1)"
  if [[ -n "$binary" ]]; then
    echo "$binary"
    return 0
  fi

  # 2. skill 目录下名为 paper-derived 的稳定二进制
  if [[ -x "$SCRIPT_DIR/paper-derived" ]]; then
    echo "$SCRIPT_DIR/paper-derived"
    return 0
  fi

  echo ""
  return 1
}

install_to() {
  local dest="$1"
  mkdir -p "$dest"
  cp "$SCRIPT_DIR/SKILL.md" "$dest/SKILL.md"
  if [[ -d "$SCRIPT_DIR/workflows" ]]; then
    mkdir -p "$dest/workflows"
    cp -r "$SCRIPT_DIR/workflows/"* "$dest/workflows/"
  fi
  if [[ -d "$SCRIPT_DIR/references" ]]; then
    mkdir -p "$dest/references"
    cp -r "$SCRIPT_DIR/references/"* "$dest/references/"
  fi
  if [[ -d "$SCRIPT_DIR/examples" ]]; then
    mkdir -p "$dest/examples"
    cp -r "$SCRIPT_DIR/examples/"* "$dest/examples/"
  fi

  # 复制二进制文件
  local binary
  binary="$(find_binary)"
  if [[ -n "$binary" ]]; then
    cp "$binary" "$dest/paper-derived"
    chmod +x "$dest/paper-derived"
    echo "二进制 → $dest/paper-derived ($(du -h "$binary" | cut -f1))"
  else
    echo "⚠ 未找到二进制文件，请先运行: ./scripts/build-cli.sh"
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