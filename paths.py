"""统一的路径解析：让项目换台电脑也能跑。

优先级：环境变量 > studio/config.json > 自动探测 > 项目内默认值

环境变量
    STUDIO_DATA      数据目录（模型、输出、临时文件）
    COMFY_ROOT       ComfyUI 根目录（含 main.py 的那一层）
    COMFY_PY         ComfyUI 的 python 解释器
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))      # studio/
BASE = os.path.dirname(HERE)                            # 项目根目录
CONFIG_PATH = os.path.join(HERE, "config.json")


def _load_config() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8-sig") as f:   # 兼容带 BOM 的文件
            return json.load(f)
    except Exception:
        return {}


CFG = _load_config()


def _pick(env: str, key: str, default: str) -> str:
    return os.environ.get(env) or CFG.get(key) or default


# ---------- 数据目录 ----------
DATA = os.path.abspath(_pick("STUDIO_DATA", "data_dir", os.path.join(BASE, "data")))
MODELS = os.path.join(DATA, "models")
OUTPUT = os.path.join(DATA, "output")
INPUT = os.path.join(DATA, "input")
TEMP = os.path.join(DATA, "temp")

# ---------- ComfyUI ----------
_CANDIDATES = [
    r"E:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI",
    os.path.join(BASE, "ComfyUI"),
    os.path.expanduser(r"~/ComfyUI"),
    r"C:\ComfyUI",
]
COMFY_ROOT = _pick("COMFY_ROOT", "comfy_root", "")
if not COMFY_ROOT or not os.path.isfile(os.path.join(COMFY_ROOT, "main.py")):
    for c in _CANDIDATES:
        if os.path.isfile(os.path.join(c, "main.py")):
            COMFY_ROOT = c
            break
else:
    COMFY_ROOT = os.path.abspath(COMFY_ROOT)

_venv = os.path.join(COMFY_ROOT, ".venv", "Scripts", "python.exe")
if not os.path.isfile(_venv):
    _venv = os.path.join(COMFY_ROOT, ".venv", "bin", "python")
COMFY_PY = _pick("COMFY_PY", "comfy_python", _venv)

COMFY_URL = _pick("COMFY_URL", "comfy_url", "http://127.0.0.1:8188")
PORT = int(_pick("PORT", "port", "8770"))


def ensure_dirs() -> None:
    for d in (DATA, MODELS, OUTPUT, INPUT, TEMP,
              os.path.join(MODELS, "checkpoints"),
              os.path.join(MODELS, "diffusion_models"),
              os.path.join(MODELS, "loras"),
              os.path.join(MODELS, "vae"),
              os.path.join(MODELS, "text_encoders"),
              os.path.join(MODELS, "clip_vision"),
              os.path.join(MODELS, "ipadapter")):
        os.makedirs(d, exist_ok=True)


def extra_model_paths_yaml(path: str | None = None) -> str:
    """生成 ComfyUI 的额外模型路径配置（每次都按当前路径重写）。"""
    ensure_dirs()
    target = path or os.path.join(HERE, "extra_model_paths.yaml")
    lines = [
        "# 由 paths.py 自动生成，请勿手改",
        "studio:",
        f"  base_path: {MODELS}",
        "  checkpoints: checkpoints",
        "  loras: loras",
        "  vae: vae",
        "  diffusion_models: diffusion_models",
        "  text_encoders: text_encoders",
        "  clip_vision: clip_vision",
        "  ipadapter: ipadapter",
        f"  custom_nodes: {os.path.join(HERE, 'custom_nodes')}",
        "",
    ]
    with open(target, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return target


def describe() -> dict:
    return {"base": BASE, "data": DATA, "comfy_root": COMFY_ROOT,
            "comfy_python": COMFY_PY, "comfy_url": COMFY_URL, "port": PORT}


if __name__ == "__main__":
    yaml_path = extra_model_paths_yaml()
    info = describe()
    info["yaml"] = yaml_path
    info["python"] = sys.version.split()[0]
    print(json.dumps(info, ensure_ascii=False, indent=2))
