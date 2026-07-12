# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['cli/paper_derived/cli.py'],
    pathex=[],
    binaries=[('/Users/zonebondx/workspace/code.research/c-checkers/paper-derived/.venv/lib/python3.10/site-packages/pypandoc/files/pandoc', '.')],
    datas=[('cli/paper_derived/prompts', 'paper_derived/prompts')],
    hiddenimports=['pypandoc', 'docx', 'openpyxl', 'pypdf', 'xlrd', 'pptx', 'fpdf'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='paper-derived',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
