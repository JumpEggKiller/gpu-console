# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['gpu_console.py'],
    pathex=[],
    # 随包捆绑 nvidia-smi(取自 repo 的 tools/,与构建机驱动无关,可复现);
    # 运行时优先用目标机系统 PATH 的 nvidia-smi,找不到才用这份。
    binaries=[('tools/nvidia-smi.exe', '.')],
    datas=[],
    hiddenimports=[],
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
    name='GPU Console',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['gpu_console.ico'],
)
