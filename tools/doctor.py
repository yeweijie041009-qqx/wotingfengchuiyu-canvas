"""环境体检：一条命令告诉你还差什么。

    python tools/doctor.py           人类可读
    python tools/doctor.py --json    给 AI / 脚本解析

检查项：Python 版本、显卡与显存、内存、磁盘、ComfyUI 路径、ComfyUI 解释器、
端口占用、模型是否齐、data 目录。
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
sys.path.insert(0, STUDIO)
import paths  # noqa: E402

MANIFEST = os.path.join(STUDIO, "models.manifest.json")


def _ok(v, msg=""):
    return {"ok": bool(v), "value": v if not isinstance(v, bool) else None, "msg": msg}


def check_python():
    v = sys.version_info
    return _ok(v >= (3, 10), f"Python {v.major}.{v.minor}.{v.micro}" +
              ("" if v >= (3, 10) else " —— 需要 3.10 以上"))


def check_gpu():
    exe = shutil.which("nvidia-smi")
    if not exe:
        return _ok(False, "找不到 nvidia-smi：没有 N 卡或驱动没装")
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=20).stdout.strip()
        name, mem = [x.strip() for x in out.split(",")[:2]]
        gb = int(mem.replace("MiB", "").strip()) / 1024
        return _ok(gb >= 7.5, f"{name} / {gb:.1f} GB 显存" +
                   ("" if gb >= 7.5 else " —— 低于 8GB，可能 OOM"))
    except Exception as e:  # noqa: BLE001
        return _ok(False, f"nvidia-smi 调用失败：{e}")


def check_ram():
    try:
        import ctypes

        class M(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        m = M()
        m.dwLength = ctypes.sizeof(M)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        gb = m.ullTotalPhys / 1024 ** 3
        return _ok(gb >= 15, f"{gb:.1f} GB 内存" + ("" if gb >= 15 else " —— 16GB 是下限"))
    except Exception:
        return _ok(True, "内存读取跳过（非 Windows）")


def check_disk():
    try:
        d = paths.DATA if os.path.exists(paths.DATA) else os.path.dirname(paths.DATA)
        drive = os.path.splitdrive(os.path.abspath(d))[0] or "C:"
        free = shutil.disk_usage(drive + "\\").free / 1024 ** 3
        return _ok(free >= 100, f"数据盘可用 {free:.0f} GB" +
                   ("" if free >= 100 else " —— 建议至少 100GB"))
    except Exception:
        return _ok(True, "磁盘读取跳过")


def check_comfy():
    root = paths.COMFY_ROOT
    if not root:
        return _ok(False, "没找到 ComfyUI：在 config.json 里设置 comfy_root")
    has_main = os.path.isfile(os.path.join(root, "main.py"))
    has_py = os.path.isfile(paths.COMFY_PY)
    msg = f"ComfyUI: {root}"
    if not has_main:
        msg += "（缺 main.py，路径不对）"
    if not has_py:
        msg += " | 找不到它的 python（comfy_python）"
    return _ok(has_main and has_py, msg)


def check_ports():
    out = {}
    for port, name in ((8188, "ComfyUI"), (paths.PORT, "画布")):
        s = socket.socket()
        s.settimeout(0.4)
        busy = s.connect_ex(("127.0.0.1", port)) == 0
        s.close()
        out[name] = {"port": port, "listening": busy}
    return _ok(True, f"8188 {'占用中' if out['ComfyUI']['listening'] else '空闲'} · "
                     f"{paths.PORT} {'占用中' if out['画布']['listening'] else '空闲'}", )


def check_models():
    if not os.path.isfile(MANIFEST):
        return _ok(False, "缺 models.manifest.json")
    with open(MANIFEST, encoding="utf-8-sig") as f:
        m = json.load(f)
    missing = []
    for group in ("required", "optional"):
        for item in m.get(group, []):
            t = os.path.join(paths.MODELS, item["dir"], item["file"])
            if not os.path.isfile(t) and paths.COMFY_ROOT:
                alt = os.path.join(paths.COMFY_ROOT, "models", item["dir"], item["file"])
                if os.path.isfile(alt):
                    t = alt
            if not os.path.isfile(t):
                missing.append(item["file"])
    need = [i for i in m.get("required", []) if i["file"] in missing]
    return _ok(not need, f"必需模型缺 {len(need)} 个" + (f"：{', '.join(x['file'] for x in need)}" if need else "，齐全"))


def run() -> dict:
    paths.ensure_dirs()
    checks = {
        "python": check_python(),
        "gpu": check_gpu(),
        "ram": check_ram(),
        "disk": check_disk(),
        "comfyui": check_comfy(),
        "ports": check_ports(),
        "models": check_models(),
    }
    return {"paths": paths.describe(), "checks": checks,
            "ready": all(c["ok"] for k, c in checks.items() if k in ("python", "gpu", "comfyui", "models"))}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    r = run()
    if "--json" in sys.argv:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r["ready"] else 1

    p = r["paths"]
    print("=" * 56)
    print(" 卧听风吹雨无限画布 · 环境体检")
    print("=" * 56)
    print(f" 项目目录 : {p['base']}")
    print(f" 数据目录 : {p['data']}")
    print(f" ComfyUI  : {p['comfy_root'] or '（未找到）'}")
    print(f" 画布端口 : {p['port']}")
    print("-" * 56)
    for name, c in r["checks"].items():
        print(f" {'[OK]  ' if c['ok'] else '[!!]  '}{c['msg']}")
    print("-" * 56)
    if r["ready"]:
        print(" 可以启动：双击 start.bat")
    else:
        print(" 还没就绪，先解决上面标 [!!] 的项。详见 说明书.md")
    return 0 if r["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
