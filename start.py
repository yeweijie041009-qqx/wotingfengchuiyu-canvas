"""一键启动：ComfyUI（后台）+ 画布后端 + 打开浏览器。

用法：
    python studio/start.py            正常启动
    python studio/start.py --no-comfy 只起画布（ComfyUI 已手动开）
    python studio/start.py --check    只打印解析到的路径
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402


def main() -> int:
    if "--check" in sys.argv:
        import json
        print(json.dumps(paths.describe(), ensure_ascii=False, indent=2))
        print("extra_model_paths.yaml ->", paths.extra_model_paths_yaml(
            os.path.join(HERE, "extra_model_paths.yaml")))
        return 0

    paths.ensure_dirs()
    procs = []

    if "--no-comfy" not in sys.argv:
        if not paths.COMFY_ROOT or not os.path.isfile(os.path.join(paths.COMFY_ROOT, "main.py")):
            print("⚠ 没找到 ComfyUI。请把 config.example.json 复制成 config.json，"
                  "把 comfy_root 指向 ComfyUI 目录（含 main.py 的那层）。")
            print("  也可以用 --no-comfy 自己先启动 ComfyUI。")
            return 2
        print("启动 ComfyUI …")
        procs.append(subprocess.Popen(
            [paths.COMFY_PY, os.path.join(HERE, "tools", "start_comfy.py")],
            cwd=HERE, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0)))

    print("启动画布后端 …")
    procs.append(subprocess.Popen([sys.executable, os.path.join(HERE, "server.py")], cwd=HERE))

    url = f"http://127.0.0.1:{paths.PORT}"
    time.sleep(3)
    print(f"\n画布地址： {url}\n按 Ctrl+C 结束\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass

    try:
        while True:
            time.sleep(1)
            if all(p.poll() is not None for p in procs):
                break
    except KeyboardInterrupt:
        print("\n正在退出 …")
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
