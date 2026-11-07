"""打包成 exe 后的入口：进程内起画布服务 + 拉起 ComfyUI + 打开浏览器。

源码模式下也可以直接运行：python studio/launcher.py
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import paths  # noqa: E402
import server  # noqa: E402

from http.server import ThreadingHTTPServer  # noqa: E402


def port_open(p: int) -> bool:
    s = socket.socket()
    s.settimeout(0.5)
    try:
        return s.connect_ex(("127.0.0.1", p)) == 0
    finally:
        s.close()


def start_comfy() -> subprocess.Popen | None:
    if port_open(8188):
        print("ComfyUI 已在运行（8188）")
        return None
    if not paths.COMFY_ROOT or not os.path.isfile(os.path.join(paths.COMFY_ROOT, "main.py")):
        print("⚠ 没找到 ComfyUI，先只启动画布。请检查 config.json 的 comfy_root。")
        return None
    script = os.path.join(paths.MEIPASS, "tools", "start_comfy.py")
    if not os.path.isfile(script):
        script = os.path.join(HERE, "tools", "start_comfy.py")
    print("启动 ComfyUI …")
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    return subprocess.Popen([paths.COMFY_PY, script], cwd=HERE, creationflags=flags)


def main() -> int:
    url = f"http://127.0.0.1:{paths.PORT}"
    if port_open(paths.PORT):
        print(f"画布已在运行：{url}")
        webbrowser.open(url)
        time.sleep(1)
        return 0

    paths.ensure_dirs()
    paths.extra_model_paths_yaml(os.path.join(paths.BASE, "extra_model_paths.yaml"))
    proc = start_comfy()

    srv = ThreadingHTTPServer(("127.0.0.1", paths.PORT), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"画布已启动：{url}")
    time.sleep(1.5)
    try:
        webbrowser.open(url)
    except Exception:
        pass

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        srv.shutdown()
        if proc and proc.poll() is None:
            proc.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
