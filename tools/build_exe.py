"""把画布打包成单文件 exe（需要本机装有 PyInstaller）。

用法：
    py -3 -m pip install pyinstaller
    py -3 tools/build_exe.py

产物：dist/wotingfengchuiyu.exe（约 15 MB），双击即启动。
注意：exe 只是启动器，ComfyUI 与模型仍需按 说明书.md 安装。
"""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("缺少 PyInstaller，请先运行：\n    py -3 -m pip install pyinstaller")
        return 2

    sep = ";"  # Windows
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile",
        "--name", "wotingfengchuiyu",
        "--distpath", os.path.join(os.path.dirname(STUDIO), "dist"),
        "--workpath", os.path.join(os.path.dirname(STUDIO), "build"),
        "--specpath", os.path.join(os.path.dirname(STUDIO), "build"),
        "--add-data", f"{os.path.join(STUDIO, 'web')}{sep}web",
        "--add-data", f"{os.path.join(STUDIO, 'skills')}{sep}skills",
        "--add-data", f"{os.path.join(STUDIO, 'tools')}{sep}tools",
        "--add-data", f"{os.path.join(STUDIO, 'models.manifest.json')}{sep}.",
        os.path.join(STUDIO, "launcher.py"),
    ]
    print("执行：\n  " + " ".join(args) + "\n")
    return subprocess.call(args)


if __name__ == "__main__":
    raise SystemExit(main())
