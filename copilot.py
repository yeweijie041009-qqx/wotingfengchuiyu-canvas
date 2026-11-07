"""画布副驾驶：一段剧本 / 一句话 → 结构化镜头表 → 前端据此铺节点。

返回的每一镜同时给出两个提示词：
  image_prompt —— 给图片模型（画面、构图、光线）
  video_prompt —— 给视频模型（动作、镜头运动、声音）
"""
from __future__ import annotations

import json

import director
import llm as llm_mod
import screenwriter

SYSTEM = """你是一名分镜师。用户会给你一段剧本或创意，你要拆成 {n} 个镜头。

只输出 JSON，不要任何解释：
{{
  "title": "片名",
  "logline": "一句话梗概",
  "shots": [
    {{
      "index": 1,
      "scene": "场景（地点 + 时间 + 环境）",
      "action": "这一镜发生了什么（一个人物、一个动作）",
      "shot_size": "远景/全景/中景/近景/特写",
      "camera": "固定机位/缓慢推近/跟随主体/横移",
      "dialogue": "台词，没有就留空",
      "image_prompt": "静态画面的完整英文描述：主体、服装、环境、光线、构图、画风",
      "video_prompt": "这一镜的动作与镜头运动的英文描述",
      "seconds": 5
    }}
  ]
}}

要求：
- 每一镜只写一个主要动作，不要塞多个动作
- image_prompt 要能单独拿去文生图，必须包含人物外观（服装/发型/体型）
- 人物外观在每一镜里保持一致
"""


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e < 0:
        raise ValueError("模型没有返回 JSON")
    return json.loads(text[s:e + 1])


import re

_H3_MARK = re.compile(r"(integrated_multimodal_description:|overall_soundscape:|"
                      r"non_diegetic_music:|\[Shot\s*\d+\]|\[镜头\s*\d+\])", re.I)


def _clean(p: str) -> str:
    """把 H3 的六段式提示词压成一句干净的画面描述（给 SDXL 用）。"""
    if not p:
        return ""
    p = re.split(r"overall_soundscape:|non_diegetic_music:", p, flags=re.I)[0]
    p = _H3_MARK.sub(" ", p)
    p = re.sub(r"\s{2,}", " ", p).strip(" ,;.")
    return p


def _norm(shots: list, style: str, seconds: float) -> list:
    out = []
    for i, s in enumerate(shots):
        img = _clean(s.get("image_prompt") or s.get("action") or "")
        vid = _clean(s.get("video_prompt") or s.get("action") or "")
        if style and style not in img:
            img = f"{img}, {style}"
        out.append({
            "index": i + 1,
            "scene": s.get("scene", ""),
            "action": s.get("action", ""),
            "shot_size": s.get("shot_size", "中景"),
            "camera": s.get("camera", "固定机位"),
            "dialogue": s.get("dialogue", ""),
            "image_prompt": img,
            "video_prompt": vid,
            "seconds": float(s.get("seconds") or seconds),
        })
    return out


def plan(text: str, n_shots: int = 4, style: str = "电影感写实风格",
         seconds: float = 5.0, llm: dict | None = None) -> dict:
    cfg = llm if (llm and llm.get("api_key")) else director.load_cfg()
    if cfg.get("api_key"):
        try:
            raw = llm_mod.complete(
                cfg,
                [{"role": "system", "content": SYSTEM.format(n=n_shots)},
                 {"role": "user", "content": f"剧本/创意：\n{text}\n\n风格：{style}"}],
                json_mode=True)
            data = raw if isinstance(raw, dict) else _parse_json(raw)
            shots = _norm(data.get("shots", [])[:n_shots], style, seconds)
            if len(shots) >= 1:
                return {"provider": "llm", "title": data.get("title", ""),
                        "logline": data.get("logline", ""), "shots": shots}
        except Exception as e:  # noqa: BLE001
            note = f"LLM 拆分失败（{e}），已退回模板分镜。"
        else:
            note = ""
    else:
        note = "未配置 API Key：用模板分镜。填了 key 才会真正按剧本拆。"

    # 兜底：用导演的模板分镜
    p = director.plan(text, n_shots, style, seconds, llm=None)
    shots = _norm([{"action": s.get("prompt", s.get("beat", "")),
                    "scene": s.get("beat", ""),
                    "image_prompt": s.get("prompt", ""),
                    "video_prompt": s.get("prompt", ""),
                    "seconds": s.get("seconds", seconds)} for s in p["shots"]],
                  style, seconds)
    return {"provider": "template", "title": p.get("title", ""),
            "logline": p.get("logline", ""), "shots": shots, "note": note}


def refine(current: dict, instruction: str, llm: dict | None = None) -> dict:
    """按用户指令修改现有分镜（聊天式）。"""
    cfg = llm if (llm and llm.get("api_key")) else director.load_cfg()
    if not cfg.get("api_key"):
        raise RuntimeError("改分镜需要 LLM：请先填 API Key（右上角 🔑）")
    ctx = json.dumps({"title": current.get("title"), "shots": current.get("shots")},
                     ensure_ascii=False)
    sys_p = (SYSTEM.split("要求：")[0] +
             "\n下面是已有的分镜 JSON，请按用户的修改意见改写，保持结构完全一致，"
             "只改需要改的部分。")
    raw = llm_mod.complete(
        cfg,
        [{"role": "system", "content": sys_p},
         {"role": "user", "content": f"已有分镜：\n{ctx}\n\n修改意见：{instruction}"}],
        json_mode=True)
    data = raw if isinstance(raw, dict) else _parse_json(raw)
    shots = _norm(data.get("shots") or current.get("shots", []),
                  current.get("style", ""), 5.0)
    return {"provider": "llm", "title": data.get("title") or current.get("title", ""),
            "logline": data.get("logline") or current.get("logline", ""),
            "shots": shots}
