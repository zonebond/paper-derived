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

uv sync

# ── 查找 Pandoc 二进制 (来自 pypandoc-binary) ──────────────────
PANDOC_BIN="$(uv run python -c "
import pypandoc, os, shutil
p = pypandoc.get_pandoc_path()
if not os.path.isabs(p):
    # pypandoc-binary: pandoc 在 pypandoc/files/ 目录下
    pkg_dir = os.path.dirname(pypandoc.__file__)
    candidate = os.path.join(pkg_dir, 'files', p)
    if os.path.isfile(candidate):
        print(candidate)
    else:
        found = shutil.which(p)
        print(found or p)
else:
    print(p)
" 2>/dev/null || true)"

if [ -z "$PANDOC_BIN" ] || [ ! -f "$PANDOC_BIN" ]; then
    echo "❌ 未找到 Pandoc 二进制。请确认 pypandoc-binary 已安装: uv sync"
    exit 1
fi

echo "Pandoc: $PANDOC_BIN ($(du -h "$PANDOC_BIN" | cut -f1))"

# ── PyInstaller 打包 ────────────────────────────────────────────
# Pandoc 打包进 onefile binary，运行时从 _MEIPASS 解压使用
uv pip install pyinstaller
uv run pyinstaller \
  --name paper-derived \
  --onefile \
  --clean \
  --noconfirm \
  --distpath build \
  --workpath build/_work \
  --add-data "cli/paper_derived/prompts:paper_derived/prompts" \
  --add-binary "${PANDOC_BIN}:." \
  --hidden-import pypandoc \
  --hidden-import docx \
  --hidden-import openpyxl \
  --hidden-import pypdf \
  --hidden-import xlrd \
  --hidden-import pptx \
  --hidden-import fpdf \
  cli/paper_derived/cli.py

# 重命名为带平台后缀的文件
mv "build/paper-derived" "build/${BINARY_NAME}"

echo ""
echo "Built: build/${BINARY_NAME} ($(du -h "build/${BINARY_NAME}" | cut -f1))"