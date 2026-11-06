"""图像生成：SDXL 文生图 + 三视图 / 分镜宫格模板。

ComfyUI 侧只用到内置节点：
CheckpointLoaderSimple -> CLIPTextEncode x2 -> EmptyLatentImage -> KSampler -> VAEDecode -> SaveImage
"""
from __future__ import annotations

import json
import urllib.request

COMFY = "http://127.0.0.1:8188"

NEG = ("lowres, blurry, jpeg artifacts, watermark, text, logo, extra limbs, extra fingers, "
       "deformed face, bad anatomy, duplicate, comic book, manga, illustration, cartoon, "
       "plastic skin, waxy skin, doll, mannequin, 3d render, cgi, airbrushed, oversaturated, "
       "nine panels, 3x3 grid, more panels than requested, frame, border, signature")

# 模板：英文为主（SDXL 的文本编码器对中文几乎无感）
TEMPLATES = {
    "single": "{prompt}",
    "turnaround": (
        "character turnaround reference sheet, the SAME character shown three times in a row: "
        "front view, side view, back view, full body, standing straight, neutral pose, "
        "consistent face and outfit across all three, plain light grey background, "
        "orthographic, even studio lighting, no perspective distortion, high detail. {prompt}"
    ),
    "grid4": (
        "storyboard contact sheet, EXACTLY FOUR equal rectangular frames arranged in a 2 by 2 grid, "
        "one horizontal white gutter and one vertical white gutter dividing the page into four quarters, "
        "four cinematic film stills telling one continuous scene in chronological order, "
        "photorealistic, 35mm, same character and same location in all four frames, consistent lighting, "
        "no text, no captions, no comic book style. {prompt}"
    ),
    "grid9": (
        "storyboard contact sheet, EXACTLY NINE equal rectangular frames arranged in a 3 by 3 grid, "
        "thin white gutters dividing the page into nine squares, "
        "nine cinematic film stills telling one continuous scene in chronological order, "
        "photorealistic, 35mm, same character and same location in every frame, consistent lighting, "
        "no text, no captions, no comic book style. {prompt}"
    ),
    "closeup": "cinematic close-up portrait, shallow depth of field, natural skin texture. {prompt}",
}

SIZES = {
    "1:1": (1024, 1024),
    "9:16": (768, 1344),
    "16:9": (1344, 768),
    "3:4": (896, 1152),
    "4:3": (1152, 896),
}


def object_info():
    with urllib.request.urlopen(COMFY + "/object_info", timeout=60) as r:
        return json.loads(r.read())


def checkpoints() -> list[str]:
    info = object_info()
    try:
        return list(info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0])
    except KeyError:
        return []


def pick_checkpoint(preferred: str | None = None) -> str | None:
    ckpts = checkpoints()
    if not ckpts:
        return None
    if preferred and preferred in ckpts:
        return preferred
    for needle in ("realvis", "juggernaut", "epicrealism", "sdxl", "sd_xl_base"):
        for c in ckpts:
            if needle.lower() in c.lower():
                return c
    return ckpts[0]


QWEN_SIZES = {
    "1:1": (1328, 1328),
    "9:16": (928, 1664),
    "16:9": (1664, 928),
    "3:4": (1140, 1472),
    "4:3": (1472, 1140),
}


def _list(info, node, field):
    try:
        return list(info[node]["input"]["required"][field][0])
    except Exception:
        return []


def pick_gguf(preferred: str | None = None) -> str | None:
    info = object_info()
    opts = _list(info, "UnetLoaderGGUF", "unet_name")
    if preferred and preferred in opts:
        return preferred
    for o in opts:
        if "qwen" in o.lower():
            return o
    return opts[0] if opts else None


def pick_text_encoder() -> str | None:
    info = object_info()
    opts = _list(info, "CLIPLoader", "clip_name")
    # 优先 Qwen2.5-VL（Qwen-Image 专用），排除 H3 用的 qwen3vl
    for o in opts:
        low = o.lower()
        if ("qwen2.5" in low or "qwen_2.5" in low) and "minimax" not in low:
            return o
    for o in opts:
        low = o.lower()
        if "qwen" in low and "minimax" not in low:
            return o
    return opts[0] if opts else None


def pick_vae(name_hint: str = "qwen") -> str | None:
    info = object_info()
    opts = _list(info, "VAELoader", "vae_name")
    for o in opts:
        if name_hint in o.lower():
            return o
    return opts[0] if opts else None


def build_qwen(
    prompt: str,
    *,
    aspect: str = "9:16",
    width: int | None = None,
    height: int | None = None,
    steps: int = 20,
    cfg: float = 2.5,
    seed: int = 0,
    prefix: str = "qwen",
) -> dict:
    """Qwen-Image（GGUF）文生图，中文原生。"""
    unet = pick_gguf()
    te = pick_text_encoder()
    vae = pick_vae()
    if not (unet and te and vae):
        raise RuntimeError("Qwen-Image 组件不全（gguf / 文本编码器 / VAE）")
    w, h = QWEN_SIZES.get(aspect, (928, 1664))
    w, h = width or w, height or h
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": unet}},
        "2": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.1}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": te, "type": "qwen_image"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": prompt}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": ""}},
        "7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {
            "model": ["2", 0], "positive": ["5", 0], "negative": ["6", 0],
            "latent_image": ["7", 0], "seed": seed, "steps": steps, "cfg": cfg,
            "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["4", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}},
    }


def build_i2i(
    prompt: str,
    ref_image: str,
    *,
    aspect: str = "9:16",
    steps: int = 30,
    cfg: float = 6.0,
    denoise: float = 0.5,
    seed: int = 0,
    ckpt: str | None = None,
    prefix: str = "i2i",
) -> dict:
    """图生图：以参考图为起点重绘，denoise 越低越像原图（锁脸用 0.35–0.55）。"""
    name = pick_checkpoint(ckpt)
    if not name:
        raise RuntimeError("没有可用的图像模型")
    w, h = SIZES.get(aspect, (768, 1344))
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": name}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": prompt}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": NEG}},
        "4": {"class_type": "LoadImage", "inputs": {"image": ref_image}},
        "5": {"class_type": "ImageScale", "inputs": {
            "image": ["4", 0], "upscale_method": "lanczos", "width": w, "height": h, "crop": "center"}},
        "6": {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
            "latent_image": ["6", 0], "seed": seed, "steps": steps, "cfg": cfg,
            "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": denoise}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["1", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": prefix}},
    }


def pick_edit_unet() -> str | None:
    info = object_info()
    opts = _list(info, "UnetLoaderGGUF", "unet_name")
    for o in opts:
        if "edit" in o.lower():
            return o
    return None


def build_qwen_edit(
    prompt: str,
    ref_images: list[str],
    *,
    aspect: str = "9:16",
    width: int | None = None,
    height: int | None = None,
    steps: int = 20,
    cfg: float = 4.0,
    seed: int = 0,
    prefix: str = "qedit",
) -> dict:
    """Qwen-Image-Edit-2509：给参考图 + 指令，保持人物身份换场景。"""
    unet = pick_edit_unet()
    te = pick_text_encoder()
    vae = pick_vae()
    if not (unet and te and vae):
        raise RuntimeError("Qwen-Image-Edit 组件不全")
    if not ref_images:
        raise RuntimeError("需要至少一张参考图")
    w, h = QWEN_SIZES.get(aspect, (928, 1664))
    w, h = width or w, height or h

    g = {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": unet}},
        "2": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.1}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": te, "type": "qwen_image"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
    }
    refs = {}
    for i, name in enumerate(ref_images[:3]):
        node_id = str(20 + i)
        g[node_id] = {"class_type": "LoadImage", "inputs": {"image": name}}
        refs[f"image{i + 1}"] = [node_id, 0]

    pos_inputs = {"clip": ["3", 0], "vae": ["4", 0], "prompt": prompt}
    neg_inputs = {"clip": ["3", 0], "vae": ["4", 0], "prompt": ""}
    pos_inputs.update(refs)
    neg_inputs.update(refs)
    g["5"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": pos_inputs}
    g["6"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": neg_inputs}
    g["7"] = {"class_type": "EmptySD3LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}}
    g["8"] = {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["5", 0], "latent": ["7", 0]}}
    g["9"] = {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["6", 0], "latent": ["7", 0]}}
    g["10"] = {"class_type": "KSampler", "inputs": {
        "model": ["2", 0], "positive": ["8", 0], "negative": ["9", 0],
        "latent_image": ["7", 0], "seed": seed, "steps": steps, "cfg": cfg,
        "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}}
    g["11"] = {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["4", 0]}}
    g["12"] = {"class_type": "SaveImage", "inputs": {"images": ["11", 0], "filename_prefix": prefix}}
    return g


def build(
    prompt: str,
    *,
    mode: str = "single",
    negative: str = NEG,
    aspect: str = "9:16",
    width: int | None = None,
    height: int | None = None,
    steps: int = 28,
    cfg: float = 6.5,
    seed: int = 0,
    sampler: str = "dpmpp_2m",
    scheduler: str = "karras",
    ckpt: str | None = None,
    prefix: str = "img",
    ref_image: str | None = None,
    ip_weight: float = 0.6,
) -> dict:
    name = pick_checkpoint(ckpt)
    if not name:
        raise RuntimeError("没有可用的图像模型，请先把 checkpoint 放进 models/checkpoints")
    w, h = SIZES.get(aspect, (768, 1344))
    w, h = width or w, height or h
    text = TEMPLATES.get(mode, "{prompt}").format(prompt=prompt).strip()

    g = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": name}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": text}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": negative}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
            "latent_image": ["4", 0], "seed": seed, "steps": steps, "cfg": cfg,
            "sampler_name": sampler, "scheduler": scheduler, "denoise": 1.0}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": prefix}},
    }
    if ref_image:
        info = object_info()
        vision = _list(info, "CLIPVisionLoader", "clip_name")
        ipa = _list(info, "IPAdapterModelLoader", "ipadapter_file")
        vision = next((v for v in vision if "vit-h" in v.lower() or "clip_vit" in v.lower()), vision[0] if vision else None)
        face_model = next((i for i in ipa if "face" in i.lower() and "sdxl" in i.lower()), None)
        ipa = face_model or next((i for i in ipa if "plus" in i.lower() and "vit-h" in i.lower()), ipa[0] if ipa else None)
        if vision and ipa:
            g["12"] = {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": vision}}
            g["13"] = {"class_type": "LoadImage", "inputs": {"image": ref_image}}
            g["14"] = {"class_type": "IPAdapterModelLoader", "inputs": {"ipadapter_file": ipa}}
            g["15"] = {"class_type": "IPAdapterAdvanced", "inputs": {
                "model": ["1", 0], "ipadapter": ["14", 0], "image": ["13", 0],
                "clip_vision": ["12", 0], "weight": ip_weight, "weight_type": "linear",
                "combine_embeds": "concat", "start_at": 0.0, "end_at": 1.0,
                "embeds_scaling": "V only"}}
            g["5"]["inputs"]["model"] = ["15", 0]
    return g
