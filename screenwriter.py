"""编剧：用「山音超级编剧大师」skill 产出分镜脚本，可直接喂给视频管线。

两种模式：
  · 配了 config.json 的 api_key → 真调 LLM，拿回结构化分镜
  · 没配 → 返回拼好的 system prompt（可贴到 Claude/GPT）+ 内置模板兜底分镜
"""
from __future__ import annotations

import json
import urllib.request

import director
import h3_prompt
import llm
import skills_loader

SKILL = "screenwriting-master"

FORMATS = {
    "ultrashort": {"label": "概念超短片 1-3 分钟", "refs": ["references/core-methodology.md", "references/format-ultrashort.md"]},
    "short": {"label": "叙事短片 5-10 分钟", "refs": ["references/core-methodology.md", "references/format-short.md"]},
    "feature": {"label": "电影长片 90 分钟", "refs": ["references/core-methodology.md", "references/format-feature.md"]},
    "series": {"label": "多集剧集", "refs": ["references/core-methodology.md", "references/format-series.md"]},
}

CONTRACT = """你现在要一次性输出一个结构化分镜。只输出 JSON，不要解释：

{
  "title": "片名",
  "logline": "一句话梗概",
  "characters": [{"name": "角色名", "want": "想要什么", "flaw": "缺陷"}],
  "shots": [
    {
      "index": 1,
      "beat": "节拍名（如：开场钩子）",
      "duration_sec": 5,
      "shot_size": "景别：远景/全景/中景/近景/特写 之一",
      "camera": "镜头运动：固定机位/缓慢推近/拉开/摇/跟随主体/缓慢环绕 之一，可加幅度与速度",
      "action": "这一镜里发生的可见动作，只写摄影机拍得到的东西",
      "dialogue": "台词（没有就留空字符串）",
      "soundscape": "环境声与动作音效（一句话）"
    }
  ]
}

硬性要求：
- 每个 shot 只写一次连续拍摄，不写剪辑点、不写转场
- 禁止心理描写、括号暗示、解释性台词；台词口语化
- action 必须是可拍摄的具体动作，不要出现"镜头语言""氛围感"这类空话
- 镜头数严格等于用户要求，duration_sec 合计接近用户要求的时长
注：视频提示词由系统按 MiniMax-H3 官方规范自动生成，你不需要写。
"""


def system_prompt(fmt: str) -> str:
    refs = FORMATS.get(fmt, FORMATS["ultrashort"])["refs"]
    return skills_loader.compose(SKILL, refs)


def _llm(messages, cfg, timeout: int = 180):
    return llm.complete(cfg, messages, json_mode=True, timeout=timeout)["data"]


CAMERAS = ["固定机位", "缓慢推近", "跟随主体", "缓慢环绕"]
SIZES = ["中景", "近景", "全景", "特写"]


def _normalize(s: dict, i: int, seconds: float, style: str) -> dict:
    """把一镜整理成结构化字段，并按 H3 官方规范预生成 h3_prompt。"""
    action = str(s.get("action", "")).strip()
    dialogue = str(s.get("dialogue", "")).strip()
    shot = {
        "index": i + 1,
        "beat": s.get("beat", ""),
        "duration_sec": float(s.get("duration_sec") or seconds),
        "shot_size": s.get("shot_size") or SIZES[i % len(SIZES)],
        "camera": s.get("camera") or CAMERAS[i % len(CAMERAS)],
        "action": action,
        "dialogue": dialogue,
        "soundscape": s.get("soundscape", "") or "环境底噪、脚步与衣物摩擦声",
    }
    shot["h3_prompt"] = h3_prompt.build(
        action, duration=shot["duration_sec"], shot_size=shot["shot_size"],
        camera=shot["camera"], dialogue=dialogue, soundscape=shot["soundscape"],
        style=style,
    )
    return shot


def _fallback(idea: str, n_shots: int, seconds: float, style: str) -> dict:
    p = director._rule_plan(idea, n_shots, style, seconds)
    shots = []
    for i, s in enumerate(p["shots"]):
        shots.append(_normalize({
            "beat": s["beat"],
            "action": f"{s['beat']}：{s['prompt'].split('。')[1] if '。' in s['prompt'] else idea}",
            "duration_sec": s["seconds"],
            "soundscape": "环境底噪、脚步与衣物摩擦声",
        }, i, seconds, style))
    return {"title": p["title"], "logline": p["logline"],
            "characters": [], "shots": shots}


def plan(idea: str, fmt: str = "ultrashort", n_shots: int = 6,
         seconds: float = 5.0, style: str = "电影感写实风格",
         llm: dict | None = None, timeout: int = 180) -> dict:
    """llm: 前端临时传入的 {api_key, base_url, model}；不传则读 config.json。"""
    fmt = fmt if fmt in FORMATS else "ultrashort"
    sys_prompt = system_prompt(fmt)
    cfg = llm if (llm and llm.get("api_key")) else director.load_cfg()

    user = (f"创意：{idea}\n格式：{FORMATS[fmt]['label']}\n"
            f"镜头数：{n_shots}\n每镜时长：约 {seconds} 秒\n风格：{style}\n\n{CONTRACT}")

    if not cfg.get("api_key"):
        return {"provider": "prompt-only", "format": fmt, "format_label": FORMATS[fmt]["label"],
                "system_prompt_chars": len(sys_prompt),
                "system_prompt": sys_prompt, "user_prompt": user,
                "storyboard": _fallback(idea, n_shots, seconds, style),
                "note": "未配置 LLM key：返回拼好的 skill 提示词 + 模板兜底分镜。"
                        "把 system_prompt 贴进 Claude/GPT 可拿到真正的 skill 产出。"}

    try:
        out = _llm([{"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user}], cfg, timeout)
        shots = []
        for i, s in enumerate(out.get("shots", [])[:n_shots]):
            shots.append(_normalize(s, i, seconds, style))
        if len(shots) < 2:
            raise ValueError("模型返回的 shots 太少")
        return {"provider": cfg.get("model", "llm"), "format": fmt,
                "format_label": FORMATS[fmt]["label"],
                "storyboard": {"title": out.get("title", ""), "logline": out.get("logline", ""),
                               "characters": out.get("characters", []), "shots": shots},
                "note": ""}
    except Exception as e:  # noqa: BLE001
        fb = _fallback(idea, n_shots, seconds, style)
        return {"provider": "fallback", "format": fmt, "format_label": FORMATS[fmt]["label"],
                "storyboard": fb, "note": f"LLM 调用失败，已用模板兜底：{e}"}


# ---------------- 长片 / 剧集：先出大纲，再展开单元 ----------------

OUTLINE_CONTRACT = """你现在只输出「大纲」，不要写分镜。只输出 JSON：

{
  "title": "片名/剧名",
  "logline": "一句话梗概",
  "characters": [{"name": "角色", "want": "想要什么", "flaw": "缺陷"}],
  "units": [
    {"index": 1, "title": "第 1 集标题 / 第 1 幕标题",
     "logline": "这一单元发生了什么，一句话",
     "beats": ["节拍1", "节拍2", "节拍3"]}
  ]
}

要求：units 数量严格等于用户要求；每个单元 logline 必须推进整体故事，不能重复；
beats 写可拍摄的事件，不写心理活动。"""

UNITS_HINT = {
    "feature": "把整部电影拆成若干「幕/序列」(sequence)，每个序列承担一段完整的戏剧功能。",
    "series": "把整部剧拆成「集」(episode)，每集要有自己的钩子、冲突与集尾钩。",
}


def outline(idea: str, fmt: str, n_units: int, llm_cfg: dict | None = None,
            minutes_per_unit: float = 3.0) -> dict:
    """长片/剧集用：先出分部大纲（幕或集），不写具体镜头。"""
    fmt = fmt if fmt in ("feature", "series") else "series"
    sys_prompt = system_prompt(fmt)
    cfg = llm_cfg if (llm_cfg and llm_cfg.get("api_key")) else director.load_cfg()
    unit_name = "集" if fmt == "series" else "个序列"

    if not cfg.get("api_key"):
        units = []
        beats_pool = ["开场钩子", "目标建立", "第一次阻力", "中点反转", "最低谷", "终局对决"]
        for i in range(n_units):
            units.append({
                "index": i + 1,
                "title": f"第 {i + 1} {unit_name}",
                "logline": f"{idea} —— 第 {i + 1} 段推进（模板占位，填 key 后由编剧 skill 生成）",
                "beats": beats_pool[:3],
            })
        return {"provider": "prompt-only", "format": fmt, "format_label": FORMATS[fmt]["label"],
                "outline": {"title": idea[:12], "logline": idea, "characters": [], "units": units},
                "note": "未配置 LLM key：这是结构占位大纲。"}

    user = (f"创意：{idea}\n格式：{FORMATS[fmt]['label']}\n"
            f"单元数：{n_units}（每个单元约 {minutes_per_unit} 分钟）\n"
            f"{UNITS_HINT.get(fmt, '')}\n\n{OUTLINE_CONTRACT}")
    try:
        data = llm.complete(cfg, [{"role": "system", "content": sys_prompt},
                                  {"role": "user", "content": user}], json_mode=True)["data"]
        units = []
        for i, u in enumerate(data.get("units", [])[:n_units]):
            units.append({
                "index": i + 1,
                "title": u.get("title", f"第 {i + 1} {unit_name}"),
                "logline": u.get("logline", ""),
                "beats": u.get("beats", [])[:6],
            })
        if not units:
            raise ValueError("大纲为空")
        return {"provider": cfg.get("model", "llm"), "format": fmt,
                "format_label": FORMATS[fmt]["label"],
                "outline": {"title": data.get("title", idea[:12]),
                            "logline": data.get("logline", idea),
                            "characters": data.get("characters", []), "units": units},
                "note": ""}
    except Exception as e:  # noqa: BLE001
        units = [{"index": i + 1, "title": f"第 {i + 1} {unit_name}",
                  "logline": f"{idea} —— 第 {i + 1} 段推进（占位）",
                  "beats": ["开场钩子", "目标建立", "第一次阻力"]}
                 for i in range(n_units)]
        return {"provider": "fallback", "format": fmt,
                "format_label": FORMATS[fmt]["label"],
                "outline": {"title": idea[:12], "logline": idea,
                             "characters": [], "units": units},
                "note": f"LLM 失败，退回占位大纲：{e}"}


def expand(idea: str, unit: dict, *, shots: int = 6, seconds: float = 5.0,
           style: str = "电影感写实风格", llm_cfg: dict | None = None,
           fmt: str = "series") -> dict:
    """把某一集/某一幕展开成镜头级分镜。"""
    cfg = llm_cfg if (llm_cfg and llm_cfg.get("api_key")) else director.load_cfg()
    ctx = f"{idea}\n本单元：{unit.get('title', '')} —— {unit.get('logline', '')}"
    beats = unit.get("beats") or []
    if beats:
        ctx += "\n节拍：" + " / ".join(beats)
    res = plan(ctx, fmt if fmt in FORMATS else "short", shots, seconds, style, llm=cfg if cfg.get("api_key") else None)
    sb = res["storyboard"]
    sb["unit"] = {"index": unit.get("index"), "title": unit.get("title")}
    return res
