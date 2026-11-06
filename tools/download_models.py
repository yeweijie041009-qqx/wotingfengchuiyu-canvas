"""按 models.manifest.json 下载模型。

用法：
    python tools/download_models.py --optional      只下可选的图片模型（能自动下载）
    python tools/download_models.py --check         只检查哪些还缺
    python tools/download_models.py --optional --host https://hf-mirror.com

说明：H3 的官方权重需要手动从 HuggingFace / ModelScope 获取（体积大、且许可需阅读），
脚本会列出清单和落盘位置；图片类模型可以直接自动下载。
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
sys.path.insert(0, STUDIO)
import paths  # noqa: E402

MANIFEST = os.path.join(STUDIO, "models.manifest.json")


def load() -> dict:
    with open(MANIFEST, encoding="utf-8-sig") as f:
        return json.load(f)


def check():
    m = load()
    paths.ensure_dirs()
    missing = []
    print(f"模型目录：{paths.MODELS}\n")
    for group in ("required", "optional"):
        print(f"[{group}]")
        for item in m.get(group, []):
            target = os.path.join(paths.MODELS, item["dir"], item["file"])
            if not os.path.isfile(target) and paths.COMFY_ROOT:
                alt = os.path.join(paths.COMFY_ROOT, "models", item["dir"], item["file"])
                if os.path.isfile(alt):
                    target = alt
            ok = os.path.isfile(target)
            size = (os.path.getsize(target) / 1e9) if ok else 0
            mark = "[OK]" if ok else "[--]"
            print(f"  {mark} {item['dir']}/{item['file']}  ({size:.1f}/{item['size_gb']} GB)  {item['role']}")
            if not ok:
                missing.append(item)
        print()
    if missing:
        print(f"还缺 {len(missing)} 个文件。")
    return missing


def download_optional(host: str):
    m = load()
    for item in m.get("optional", []):
        if "hf_repo" not in item:
            continue
        cmd = [sys.executable, os.path.join(HERE, "get_model.py"),
               item["hf_repo"], item["hf_path"], item["dir"], "--host", host]
        print("→", " ".join(cmd))
        rc = os.spawnv(os.P_WAIT, sys.executable, cmd)
        if rc != 0:
            print(f"  ⚠ 下载失败：{item['file']}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    host = "https://hf-mirror.com"
    if "--host" in sys.argv:
        host = sys.argv[sys.argv.index("--host") + 1]

    missing = check()
    if "--check" in sys.argv:
        return 0 if not missing else 1
    if "--optional" in sys.argv:
        download_optional(host)
        check()
        return 0
    print("需要手动下载的（官方 H3 权重）：")
    for item in missing:
        if "hf_repo" not in item:
            print(f"  - {item['file']}  →  {item['source']}")
            print(f"    放到：{os.path.join(paths.MODELS, item['dir'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
