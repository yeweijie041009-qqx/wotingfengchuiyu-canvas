"""Minimal ComfyUI client + MiniMax-H3 graph builder (stdlib only).

Talks to a local ComfyUI at 127.0.0.1:8188 and builds an API-format graph for
the installed `ComfyUI-MiniMaxH3-Easy-Unified` nodes:

    MiniMaxH3EasyLoader -> MiniMaxH3Easy -> MiniMaxH3EasyOutput
                                          -> (optional turbo LoRA) -> (optional sigma shift)
                                          -> KSampler -> VAEDecode / VAEDecodeAudio
                                          -> CreateVideo -> SaveVideo
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

import paths
COMFY = paths.COMFY_URL


def _req(path: str, payload=None, timeout=30, retries=3):
    """高负载时 ComfyUI 的 HTTP 会短暂拒绝连接，这里做退避重试。"""
    url = COMFY + path
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
            return json.loads(body) if body else {}
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt + 1 < retries:
                time.sleep(2 * (attempt + 1))
    raise last  # type: ignore[misc]


def alive(timeout: float = 2.0, retries: int = 1) -> bool:
    """快速探活：单次请求，不重试，避免把 /api/health 拖住。"""
    try:
        _req("/system_stats", timeout=timeout, retries=retries)
        return True
    except Exception:
        return False


_info_cache = None


def object_info(force=False):
    global _info_cache
    if _info_cache is None or force:
        _info_cache = _req("/object_info", timeout=60)
    return _info_cache


def _first_combo(info, node, field, default=None):
    spec = info.get(node, {}).get("input", {}).get("required", {}).get(field)
    if not spec:
        return default
    val = spec[0]
    if isinstance(val, list) and val:
        return val[0]
    return default


def _pick(options, *needles, default=None):
    for opt in options or []:
        low = str(opt).lower()
        if all(n.lower() in low for n in needles):
            return opt
    return default


class Models:
    """Resolved file names and enum values for this install."""

    def __init__(self, info):
        req = info["MiniMaxH3EasyLoader"]["input"]["required"]
        self.fl2va = _pick(req["fl2va_model"][0], "fl2va", default=req["fl2va_model"][0][0])
        self.ref2va = _pick(req["ref2va_model"][0], "ref2va", default=req["ref2va_model"][0][0])
        self.text_encoder = _pick(req["text_encoder"][0], "qwen", default=req["text_encoder"][0][0])
        self.video_vae = _pick(req["video_vae"][0], "video_vae", default=req["video_vae"][0][0])
        self.audio_vae = _pick(req["audio_vae"][0], "audio_vae", default=req["audio_vae"][0][0])

        easy = info["MiniMaxH3Easy"]["input"]["required"]
        self.resolutions = list(easy["resolution"][0])
        self.aspects = list(easy["aspect_ratio"][0])

        self.loras = []
        if "LoraLoaderModelOnly" in info:
            self.loras = list(info["LoraLoaderModelOnly"]["input"]["required"]["lora_name"][0])
        self.lora_8step = _pick(self.loras, "8step")
        self.lora_4step = _pick(self.loras, "4step") or _pick(self.loras, "turbo")
        self.turbo_lora = self.lora_8step or self.lora_4step
        self.has_shift = "MiniMaxH3SigmaShift" in info
        self.has_savevideo = "SaveVideo" in info
        self.has_createvideo = "CreateVideo" in info
        self.samplers = list(info.get("KSampler", {}).get("input", {}).get("required", {})
                             .get("sampler_name", [["euler"]])[0])
        self.schedulers = list(info.get("KSampler", {}).get("input", {}).get("required", {})
                               .get("scheduler", [["simple"]])[0])

    def as_dict(self):
        return {
            "fl2va": self.fl2va, "ref2va": self.ref2va, "text_encoder": self.text_encoder,
            "video_vae": self.video_vae, "audio_vae": self.audio_vae,
            "resolutions": self.resolutions, "aspects": self.aspects,
            "turbo_lora": self.turbo_lora, "has_shift": self.has_shift,
            "samplers": self.samplers, "schedulers": self.schedulers,
        }


def models() -> Models:
    return Models(object_info())


# 质量档：草稿 / 标准 / 精细
PRESETS = {
    "draft":    {"resolution": "360P", "steps": 4, "lora": "4step"},
    "standard": {"resolution": "480P", "steps": 8, "lora": "8step"},
    "fine":     {"resolution": "720P", "steps": 8, "lora": "8step"},
}


def resolve_preset(name: str, m: Models | None = None):
    """返回 (resolution, steps, lora_name)。未知档位按 standard 处理。"""
    m = m or models()
    p = PRESETS.get((name or "standard").lower(), PRESETS["standard"])
    lora = m.lora_8step if p["lora"] == "8step" else m.lora_4step
    return p["resolution"], p["steps"], lora


def build_graph(
    prompt: str,
    *,
    mode: str = "t2va",
    resolution: str | None = None,
    aspect: str | None = None,
    width: int = 864,
    height: int = 480,
    seconds: float = 5.0,
    fps: float = 24.0,
    seed: int = 0,
    steps: int = 4,
    cfg: float = 1.0,
    use_turbo: bool = True,
    turbo_strength: float = 0.7,
    lora: str | None = None,
    shift_video: float = 12.0,
    shift_audio: float = 3.0,
    prefix: str = "h3",
    image: str | None = None,
    m: Models | None = None,
) -> dict:
    m = m or models()
    resolution = resolution or ("360P" if "360P" in m.resolutions else m.resolutions[0])
    aspect = aspect or ("9:16" if "9:16" in m.aspects else m.aspects[0])
    lora_name = lora or m.turbo_lora
    if image:
        mode = "ref2va" if mode == "ref2va" else "i2va"

    g: dict = {
        "1": {"class_type": "MiniMaxH3EasyLoader", "inputs": {
            "fl2va_model": m.fl2va, "ref2va_model": m.ref2va, "text_encoder": m.text_encoder,
            "video_vae": m.video_vae, "audio_vae": m.audio_vae}},
        "2": {"class_type": "MiniMaxH3Easy", "inputs": {
            "h3_bundle": ["1", 0], "mode": mode, "prompt": prompt,
            "resolution": resolution, "aspect_ratio": aspect,
            "width": width, "height": height, "seconds": float(seconds),
            "advanced": False, "fps": float(fps),
            "keyframe_role": "first", "ref_image_size": "1k",
            "reference_mention_mode": "index"}},
        "3": {"class_type": "MiniMaxH3EasyOutput", "inputs": {"h3_context": ["2", 1]}},
    }

    model_src = ["2", 0]
    if use_turbo and lora_name:
        g["4"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
            "model": model_src, "lora_name": lora_name, "strength_model": turbo_strength}}
        model_src = ["4", 0]
    if m.has_shift:
        g["5"] = {"class_type": "MiniMaxH3SigmaShift", "inputs": {
            "model": model_src, "shift_video": shift_video, "shift_audio": shift_audio}}
        model_src = ["5", 0]

    if image:
        g["12"] = {"class_type": "LoadImage", "inputs": {"image": image}}
        g["2"]["inputs"]["media_1"] = ["12", 0]
        g["2"]["inputs"]["media_type_1"] = "image"

    g["6"] = {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["3", 0]}}
    g["7"] = {"class_type": "KSampler", "inputs": {
        "model": model_src, "seed": seed, "steps": steps, "cfg": cfg,
        "sampler_name": "euler", "scheduler": "simple",
        "positive": ["3", 0], "negative": ["6", 0],
        "latent_image": ["3", 1], "denoise": 1.0}}
    g["8"] = {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 2]}}
    g["9"] = {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["7", 0], "vae": ["3", 3]}}
    g["10"] = {"class_type": "CreateVideo", "inputs": {
        "images": ["8", 0], "audio": ["9", 0], "fps": ["3", 4], "bit_depth": 8}}
    g["11"] = {"class_type": "SaveVideo", "inputs": {
        "video": ["10", 0], "filename_prefix": prefix, "format": "auto", "codec": "auto"}}
    return g


def submit(graph: dict) -> str:
    try:
        res = _req("/prompt", {"prompt": graph, "client_id": "dsh-studio"})
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")[:1200]
        except Exception:
            pass
        raise RuntimeError(f"提交失败 HTTP {e.code}: {detail}") from e
    if "error" in res or "node_errors" in res and res["node_errors"]:
        raise RuntimeError(json.dumps(res, ensure_ascii=False, indent=2))
    return res["prompt_id"]


def queue_state():
    try:
        q = _req("/queue")
        return {"running": len(q.get("queue_running", [])), "pending": len(q.get("queue_pending", []))}
    except Exception as e:
        return {"error": str(e)}


def wait(prompt_id: str, on_tick=None, poll=2.0, timeout=7200):
    start = time.time()
    misses = 0
    while True:
        try:
            hist = _req(f"/history/{prompt_id}", retries=2)
            misses = 0
        except Exception:
            # 生成高峰期间歇性拒绝连接，不算失败，继续等
            misses += 1
            if misses > 120:
                raise TimeoutError(f"ComfyUI 连续 {misses} 次不可达")
            time.sleep(poll)
            continue
        if prompt_id in hist:
            entry = hist[prompt_id]
            st = entry.get("status", {}) or {}
            if st.get("status_str") == "error":
                detail = ""
                for msg in st.get("messages", []):
                    if isinstance(msg, list) and msg and msg[0] == "execution_error":
                        detail = (msg[1] or {}).get("exception_message", "")
                        break
                raise RuntimeError("ComfyUI 执行失败：" + (detail or "未知错误")[:600])
            return {
                "elapsed": round(time.time() - start, 1),
                "status": st,
                "outputs": entry.get("outputs", {}),
            }
        if time.time() - start > timeout:
            raise TimeoutError(f"job {prompt_id} exceeded {timeout}s")
        if on_tick:
            on_tick(round(time.time() - start, 1))
        time.sleep(poll)


def files_from(result: dict):
    out = []
    for node_out in result.get("outputs", {}).values():
        for key in ("images", "videos", "gifs", "audio"):
            for item in node_out.get(key, []) or []:
                out.append(item)
    return out
