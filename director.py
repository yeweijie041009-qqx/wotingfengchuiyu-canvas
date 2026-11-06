"""导演：一句话 → 分镜脚本（可接任意 OpenAI 兼容模型，无 key 时用内置模板）。

返回结构：
{
  "title": str, "logline": str, "provider": "deepseek"|"local",
  "shots": [{"index": 1, "beat": "开场", "prompt": "...", "seconds": 5}, ...]
}
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

import h3_prompt
import llm

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "config.json")

BEATS = ["开场", "铺垫", "转折", "高潮", "收束", "余韵", "延伸", "尾声"]
CAMERA = [
    "固定机位中景，平视，浅景深",
    "缓推近景，略低角度，景深收紧",
    "手持跟拍，轻微晃动，广角",
    "侧逆光特写，长焦压缩背景",
    "低机位仰拍，环境纵深明显",
    "环绕运镜半圈，中近景",
]
LIGHT = [
    "冷调夜景，霓虹与湿地面反光",
    "暖色室内光，台灯主光，暗部保留细节",
    "清晨侧光，空气中有浮尘",
    "阴天散射光，低饱和",
    "顶光偏硬，人物面部有阴影层次",
    "夕照逆光，轮廓光勾边",
]


def load_cfg() -> dict:
    if not os.path.isfile(CFG):
        return {}
    try:
        with open(CFG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _llm(prompt: str, cfg: dict) -> dict:
    return llm.complete(cfg, [
        {"role": "system", "content": "你是短剧导演，只输出 JSON，不解释。"},
        {"role": "user", "content": prompt},
    ], json_mode=True)["data"]


SYS = """把用户的一句话创意拆成 {n} 个镜头，用于 AI 视频模型（有台词和音效，没有后期）。
每个镜头必须是一次连续拍摄、无剪辑。只输出 JSON：
{{"title":"剧名","logline":"一句话梗概","shots":[
 {{"beat":"开场","seconds":5,"prompt":"镜头描述"}}]}}
prompt 用中文写，必须包含：景别与机位、人物外观、动作、光线与色调、环境；
结尾另起一行写 "overall_soundscape: 环境声描述"；
若有台词，写在 <d>[Chinese] 台词</d> 里。每个 prompt 不超过 220 字。"""


def _rule_plan(idea: str, n: int, style: str, seconds: float) -> dict:
    idea = (idea or "").strip() or "一个普通人在平凡的一天里做了一个不平凡的决定"
    core = idea.rstrip("。！？.!?")
    shots = []
    for i in range(n):
        beat = BEATS[i % len(BEATS)]
        cam = CAMERA[i % len(CAMERA)]
        light = LIGHT[i % len(LIGHT)]
        if i == 0:
            action = f"画面从环境中切入：{core}。人物进入画面，动作克制，留出呼吸感"
        elif i == n - 1:
            action = f"故事收束：{core} 的结果显现，人物静止片刻，情绪落在眼神上"
        else:
            action = f"推进情节：围绕「{core}」展开第 {i} 个动作转折，人物有明显但不过度的动作"
        # 统一交给 H3 提示词规范器生成最终提示词，保证格式一致
        prompt = h3_prompt.build(
            action + f"。光线：{light}。",
            duration=seconds,
            shot_size="中景" if i % 2 == 0 else "近景",
            camera=cam,
            soundscape="与画面匹配的环境声、人物呼吸与衣物摩擦声，音量克制",
            style=style,
        )
        shots.append({"index": i + 1, "beat": beat, "seconds": seconds,
                      "action": action, "camera": cam, "light": light,
                      "prompt": prompt})
    return {"title": core[:16], "logline": core, "provider": "local", "shots": shots}


def plan(idea: str, n_shots: int = 5, style: str = "电影感写实风格",
         seconds: float = 5.0, llm: dict | None = None) -> dict:
    cfg = llm if (llm and llm.get("api_key")) else load_cfg()
    if cfg.get("api_key"):
        try:
            out = _llm(SYS.format(n=n_shots) + "\n创意：" + idea, cfg)
            shots = []
            for i, s in enumerate(out.get("shots", [])[:n_shots]):
                shots.append({
                    "index": i + 1,
                    "beat": s.get("beat", BEATS[i % len(BEATS)]),
                    "seconds": float(s.get("seconds", seconds)),
                    "prompt": s.get("prompt", "").strip(),
                })
            if len(shots) >= 2:
                return {"title": out.get("title", idea[:16]),
                        "logline": out.get("logline", idea),
                        "provider": cfg.get("model", "llm"), "shots": shots}
        except Exception as e:  # noqa: BLE001
            fb = _rule_plan(idea, n_shots, style, seconds)
            fb["note"] = f"LLM 调用失败，已用模板导演：{e}"
            return fb
    return _rule_plan(idea, n_shots, style, seconds)


if __name__ == "__main__":
    import sys
    print(json.dumps(plan(sys.argv[1] if len(sys.argv) > 1 else "", 5),
                     ensure_ascii=False, indent=2))
