"""从 hf-mirror.com 下载模型到 ComfyUI，支持断点续传。

用法：
    python tools/get_model.py <repo> <filename> <target_subdir> [--host https://hf-mirror.com]
例：
    python tools/get_model.py stabilityai/stable-diffusion-xl-base-1.0 \
        sd_xl_base_1.0.safetensors checkpoints
"""
from __future__ import annotations

import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths
COMFY_MODELS = paths.MODELS
STUDIO_MODELS = r"C:\Users\29754\Documents\deepseek-harness\default-workspace\studio\models"


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    repo, filename, subdir = sys.argv[1], sys.argv[2], sys.argv[3]
    host = "https://hf-mirror.com"
    if "--host" in sys.argv:
        host = sys.argv[sys.argv.index("--host") + 1]
    root = COMFY_MODELS
    if "--root" in sys.argv:
        root = sys.argv[sys.argv.index("--root") + 1]

    dest_dir = os.path.join(root, subdir)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(filename))
    url = f"{host}/{repo}/resolve/main/{filename}"

    have = os.path.getsize(dest) if os.path.exists(dest) else 0
    t0 = time.time()
    total = 0
    for attempt in range(20):
        have = os.path.getsize(dest) if os.path.exists(dest) else 0
        req = urllib.request.Request(url, headers={"User-Agent": "dsh-studio/1.0"})
        if have:
            req.add_header("Range", f"bytes={have}-")
        try:
            r = urllib.request.urlopen(req, timeout=60)
            total = int(r.headers.get("Content-Length") or 0) + have
            mode = "ab" if have and r.status == 206 else "wb"
            if mode == "wb":
                have = 0
            done = have
            last = time.time()
            with open(dest, mode) as f:
                while True:
                    chunk = r.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if time.time() - last > 15:
                        last = time.time()
                        speed = (done - have) / max(1e-6, time.time() - t0)
                        eta = (total - done) / speed if speed > 0 else 0
                        print(f"{human(done)}/{human(total)} {human(speed)}/s ETA {int(eta)}s", flush=True)
            r.close()
        except Exception as e:  # noqa: BLE001
            print(f"retry {attempt + 1}: {type(e).__name__}", flush=True)
            time.sleep(3)
            continue
        if total and os.path.getsize(dest) >= total:
            break

    size = os.path.getsize(dest)
    print(f"done {human(size)} / {human(total)} in {int(time.time() - t0)}s", flush=True)
    return 0 if (not total or size >= total) else 1


if __name__ == "__main__":
    raise SystemExit(main())
