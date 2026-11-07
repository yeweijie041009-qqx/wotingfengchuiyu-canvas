"""画布副驾驶：一段剧本 / 一句话 → 结构化镜头表 → 前端据此铺节点。

这里**不自己写分镜**，而是复用两套 skill：
  · 山音超级编剧大师（screenwriter）—— 写分镜、台词、景别
  · MiniMax H3 提示词规范（h3_prompt）—— 把每一镜拼成官方格式的视频提示词

输出给前端的每一镜包含：
  image_prompt —— 干净的画面描述（给 SDXL 出关键帧）
  video_prompt —— H3 官方格式（镜头运动 / 说话人 / 台词标签 / 音效）
"""
from __future__ import annotations

import json
import re

import director
import h3_prompt
import llm as llm_mod
import screenwriter

_H3_MARK = re.compile(r"(integrated_multimodal_description:|overall_soundscape:|"
                      r"non_diegetic_music:|\[Shot\s*\d+\]|\[镜头\s*\d+\])", re.I)


def _clean(p: str) -> str:
    """把 H3 六段式提示词压成一句干净画面描述（给图片模型用）。"""
    if not p:
        return ""
    p = re.split(r"overall_soundscape:|non_diegetic_music:", p, flags=re.I)[0]
    p = _H3_MARK.sub(" ", p)
    p = re.sub(r"^(画面|镜头|场景|动作|整段)[：:]\s*", "", p)
    # 去掉模板里夹带的元信息段落（整段/标题/创意/风格）
    segs = [x.strip() for x in p.split("。")
            if x.strip() and not re.match(r"(整段|标题|创意|风格|格式)[：:]", x.strip())]
    p = "。".join(segs)
    p = re.sub(r"\s{2,}", " ", p).strip(" ,;.。")
    return p[:160]


def plan(text: str, n_shots: int = 4, style: str = "电影感写实风格",
         seconds: float = 5.0, llm: dict | None = None,
         fmt: str = "ultrashort") -> dict:
    """走 screenwriter（山音 skill）拿分镜，h3_prompt 负责视频提示词。"""
    note = ""
    try:
        sp = screenwriter.plan(text, fmt, n_shots, seconds, style, llm=llm, timeout=110)
        sb = sp["storyboard"]
        shots = []
        for s in sb["shots"]:
            action = s.get("action", "")
            shots.append({
                "index": s["index"],
                "scene": s.get("beat", ""),
                "action": action,
                "beat": s.get("beat", ""),
                "shot_size": s.get("shot_size", "中景"),
                "camera": s.get("camera", "固定机位"),
                "dialogue": s.get("dialogue", ""),
                "soundscape": s.get("soundscape", ""),
                # 视频提示词：H3 官方格式（screenwriter 里已经生成）
                "video_prompt": s.get("h3_prompt") or h3_prompt.build(
                    action, duration=float(s.get("duration_sec", seconds)),
                    shot_size=s.get("shot_size", "中景"), camera=s.get("camera", ""),
                    dialogue=s.get("dialogue", ""), soundscape=s.get("soundscape", ""),
                    style=style),
                # 图片提示词：干净画面描述
                "image_prompt": _clean(f"{action}。{s.get('beat', '')}。{style}"),
                "seconds": float(s.get("duration_sec") or seconds),
            })
        if shots:
            return {
                "provider": sp.get("provider", "template"),
                "skill": "山音编剧 + H3 提示词规范",
                "title": sb.get("title", ""),
                "logline": sb.get("logline", ""),
                "shots": shots,
                "note": sp.get("note", ""),
            }
        note = "编剧 skill 没返回镜头，已退回模板分镜。"
    except Exception as e:  # noqa: BLE001
        note = f"skill 调用失败（{e}），已退回模板分镜。"

    # 兜底：规则导演 + H3 提示词规范
    p = director.plan(text, n_shots, style, seconds, llm=None)
    shots = []
    for i, s in enumerate(p["shots"]):
        action = s.get("prompt", "")
        shots.append({
            "index": i + 1, "scene": s.get("beat", ""), "action": action,
            "beat": s.get("beat", ""), "shot_size": "中景", "camera": "固定机位",
            "dialogue": "",
            "video_prompt": h3_prompt.build(action, duration=float(s.get("seconds", seconds)),
                                            style=style),
            "image_prompt": _clean(f"{action}。{style}"),
            "seconds": float(s.get("seconds", seconds)),
        })
    return {"provider": "template", "skill": "模板导演 + H3 提示词规范",
            "title": p.get("title", ""), "logline": p.get("logline", ""),
            "shots": shots, "note": note}


def refine(current: dict, instruction: str, llm: dict | None = None,
           fmt: str = "ultrashort") -> dict:
    """按用户意见改分镜：用同一个编剧 skill 的 system prompt，保证风格一致。"""
    cfg = llm if (llm and llm.get("api_key")) else director.load_cfg()
    if not cfg.get("api_key"):
        raise RuntimeError("改分镜需要 LLM：请先填 API Key（右上角 🔑）")

    sys_p = screenwriter.system_prompt(fmt)
    ctx = json.dumps({
        "title": current.get("title"),
        "logline": current.get("logline"),
        "shots": [{k: v for k, v in s.items()
                   if k in ("index", "beat", "shot_size", "camera",
                            "action", "dialogue", "soundscape", "duration_sec")}
                  for s in current.get("shots", [])],
    }, ensure_ascii=False)

    raw = llm_mod.complete(
        cfg,
        [{"role": "system", "content": sys_p},
         {"role": "user", "content":
          f"已有分镜：\n{ctx}\n\n按这个修改意见改一版，结构与字段保持一致：\n{instruction}"}],
        json_mode=True, timeout=60)

    data = raw if isinstance(raw, dict) else (raw.get("storyboard") or raw)
    shots_in = data.get("shots") or current.get("shots", [])
    shots = []
    for i, s in enumerate(shots_in):
        action = s.get("action", "")
        secs = float(s.get("duration_sec") or s.get("seconds") or 5)
        shots.append({
            "index": i + 1,
            "scene": s.get("beat", ""),
            "action": action,
            "beat": s.get("beat", ""),
            "shot_size": s.get("shot_size", "中景"),
            "camera": s.get("camera", "固定机位"),
            "dialogue": s.get("dialogue", ""),
            "soundscape": s.get("soundscape", ""),
            "video_prompt": s.get("h3_prompt") or h3_prompt.build(
                action, duration=secs, shot_size=s.get("shot_size", "中景"),
                camera=s.get("camera", ""), dialogue=s.get("dialogue", ""),
                soundscape=s.get("soundscape", ""), style=""),
            "image_prompt": _clean(f"{action}。{s.get('beat', '')}"),
            "seconds": secs,
        })
    return {"provider": "llm", "skill": "山音编剧 + H3 提示词规范",
            "title": data.get("title") or current.get("title", ""),
            "logline": data.get("logline") or current.get("logline", ""),
            "shots": shots}

CHAR_SYSTEM = """你是角色设计师。根据下面的分镜，提炼出**同一个主角**的外观设定。

只输出 JSON：
{
  "image_prompt": "英文，一张角色设定图：全身正面站姿、纯色背景、清晰五官与服装细节、同一画风",
  "subject": "中文一句话，写死这个人的外观：年龄、发型、体型、服装、标志性特征",
  "name": "角色名"
}

要求：
- 只描述**一个**主角（分镜里最主要的那个）
- 外观必须具体到可以被反复画出来（发型颜色、衣服款式与颜色、体型、配饰）
- 不要写场景、动作、光线
"""


def character(pl: dict, llm: dict | None = None) -> dict:
    """根据分镜产出「角色设定」：一张定妆图的提示词 + 一段锁人用的主体描述。"""
    cfg = llm if (llm and llm.get("api_key")) else director.load_cfg()
    shots = pl.get("shots", [])
    brief = json.dumps([{k: s.get(k, "") for k in ("action", "scene", "beat")} for s in shots],
                       ensure_ascii=False)

    if cfg.get("api_key"):
        try:
            raw = llm_mod.complete(
                cfg,
                [{"role": "system", "content": CHAR_SYSTEM},
                 {"role": "user", "content": f"片名：{pl.get('title','')}\n梗概：{pl.get('logline','')}\n分镜：{brief}"}],
                json_mode=True, timeout=60)
            data = raw if isinstance(raw, dict) else json.loads(raw)
            if data.get("image_prompt"):
                return {"provider": "llm", "name": data.get("name", "主角"),
                        "image_prompt": data["image_prompt"],
                        "subject": data.get("subject", "")}
        except Exception:
            pass

    # 兜底：用第一镜的描述反推
    base = (shots[0].get("image_prompt") if shots else "") or "主角"
    return {
        "provider": "template", "name": "主角",
        "image_prompt": ("character design sheet, full body, front view, neutral pose, "
                         f"plain light background, detailed outfit, {base}"),
        "subject": base[:80],
    }