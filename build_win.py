# -*- coding: utf-8 -*-
"""Windows 一键构建:PyInstaller + Inno Setup → installer/GPU Console Setup.exe
在 CI 里由 GitHub Actions 调用;本地也可直接: python build_win.py"""
import os
import platform
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

def run(cmd, **kw):
    print("$", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT, **kw)

# 1) PyInstaller(优先用本机 Python3.14,退回当前解释器)
py = r"C:\Users\micasa\AppData\Local\Programs\Python\Python314\python.exe"
if not os.path.exists(py):
    py = sys.executable
run([py, "-m", "PyInstaller", "GPU Console.spec", "--noconfirm"])

# 2) Inno Setup(ISCC 路径:用户级 > Program Files > 下载)
iss = os.path.join(ROOT, "gpu_console.iss")
cands = [
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
    os.path.join(ROOT, "innosetup", "ISCC.exe"),
]
iscc = next((c for c in cands if os.path.exists(c)), None)
if not iscc:
    raise SystemExit("找不到 ISCC.exe,请安装 Inno Setup 6")
run([iscc, iss])
print("OK: installer/GPU Console Setup.exe")
