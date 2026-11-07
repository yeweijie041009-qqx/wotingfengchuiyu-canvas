"""模型档案（profile）：把「用哪个模型」做成可配置的 JSON，而不是写死在代码里。

一份 profile = 一个 ComfyUI API 工作流 + 参数映射 + 依赖的模型文件清单。

    profiles/<id>.json
    {
      "id": "h3-video",
      "name": "MiniMax-H3",
      "kind": "video",              // video / image
      "desc": "…",
      "requires": [{"dir":"diffusion_models","file":"xxx.safetensors"}],
      "params": {                    // 参数名 → 图里哪个节点的哪个输入
        "prompt":  {"node":"2","input":"prompt"},
        "seconds": {"node":"2","input":"seconds","type":"float"},
        "seed":    {"node":"7","input":"seed","type":"int"},
        "steps":   {"node":"7","input":"steps","type":"int"}
      },
      "image": {                     // 可选：挂了首帧图时怎么接
        "load_node":"12","target_node":"2","target_input":"media_1","set_mode":"i2va"
      },
      "graph": { … }                 // ComfyUI /prompt 的 API 格式图
    }

用户想换模型：把模型丢进 models/ 对应目录，再写一份 profile 指向它即可。
"""
from __future__ import annotations

import copy
import json
import os

import paths

PROFILE_DIR = os.path.join(paths.MEIPASS if paths.FROZEN else os.path.dirname(os.path.abspath(__file__)),
                           "profiles")


def _paths() -> str:
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles")
    return d if os.path.isdir(d) else PROFILE_DIR


def list_profiles() -> list[dict]:
    out = []
    d = _paths()
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, fn), encoding="utf-8-sig") as f:
                p = json.load(f)
        except Exception:
            continue
        out.append(_summary(p))
    return out


def _summary(p: dict) -> dict:
    missing = []
    for r in p.get("requires", []):
        if not _model_exists(r["dir"], r["file"]):
            missing.append(f"{r['dir']}/{r['file']}")
    return {
        "id": p.get("id"), "name": p.get("name", p.get("id")),
        "kind": p.get("kind", "video"), "desc": p.get("desc", ""),
        "requires": p.get("requires", []),
        "missing": missing, "ready": not missing,
    }


def _model_exists(subdir: str, filename: str) -> bool:
    if os.path.isfile(os.path.join(paths.MODELS, subdir, filename)):
        return True
    if paths.COMFY_ROOT:
        return os.path.isfile(os.path.join(paths.COMFY_ROOT, "models", subdir, filename))
    return False


def load(profile_id: str) -> dict:
    p = os.path.join(_paths(), f"{profile_id}.json")
    if not os.path.isfile(p):
        raise FileNotFoundError(f"没有这个模型档案：{profile_id}")
    with open(p, encoding="utf-8-sig") as f:
        return json.load(f)


def build(profile_id: str, values: dict, image_name: str | None = None) -> dict:
    """按档案生成 ComfyUI API 图。values 里只放认识的参数名。"""
    p = load(profile_id)
    graph = copy.deepcopy(p["graph"])
    params = p.get("params", {})

    for key, spec in params.items():
        if key not in values or values[key] is None:
            continue
        node = graph.get(str(spec["node"]))
        if not node:
            continue
        val = values[key]
        t = spec.get("type")
        if t == "int":
            val = int(val)
        elif t == "float":
            val = float(val)
        node["inputs"][spec["input"]] = val

    if image_name and p.get("image"):
        spec = p["image"]
        node_id = str(spec.get("load_node", "12"))
        graph[node_id] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
        target = graph.get(str(spec["target_node"]))
        if target:
            target["inputs"][spec["target_input"]] = [node_id, 0]
            if spec.get("set_mode"):
                target["inputs"]["mode"] = spec["set_mode"]
    return graph
