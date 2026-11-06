"""把镜头数据写成 MiniMax-H3 官方规定的提示词结构。

依据 skills/minimax-h3/h3-prompt-writing/references/base-en.txt：
  1. 关键帧模式先写对齐指令（I2VA/FL2VA/L2VA）
  2. integrated_multimodal_description: [Shot 1] 风格、景别、主体、动作、镜头运动
     - 后续镜头用 "[Shot 2] At 00:03.500, the camera cuts to ..."
     - 镜头运动写成「类型 + 幅度 + 速度」的自然语句
     - 台词用 <d>[Chinese] ...</d>，说话人用稳定 ID (S1)
  3. overall_soundscape: 1-4 句
  4. non_diegetic_music: 1-3 句或 N/A
"""
from __future__ import annotations

import re

# 中文镜头语言 → 官方词汇（已按第三人称单数写好，直接拼成句子）
CAMERA_WORDS = [
    ("推", "pushes in"), ("拉", "pulls out"), ("摇", "pans"), ("移", "trucks"),
    ("跟", "tracks the subject"), ("环绕", "arcs around the subject"), ("绕", "arcs around the subject"),
    ("升降", "pedestals"), ("固定", "holds a static shot"), ("静", "holds a static shot"),
    ("手持", "shakes slightly"), ("晃", "shakes slightly"), ("第一人称", "holds a POV"),
]

SHOT_SIZE = {
    "远景": "a wide shot", "全景": "a full shot", "中景": "a medium shot",
    "近景": "a close shot", "特写": "a close-up", "大特写": "an extreme close-up",
}


def _camera_phrase(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "The camera holds a static shot."
    verb = None
    for cn, phrase in CAMERA_WORDS:
        if cn in t:
            verb = phrase
            break
    if verb is None:
        return f"The camera moves slowly as described in the shot."
    if verb == "holds a static shot":
        return "The camera holds a static shot."
    amp = "with small amplitude " if ("小" in t or "轻" in t or "缓" in t) else ""
    speed = "at slow speed" if ("缓" in t or "慢" in t) else ("at fast speed" if "快" in t else "")
    tail = " ".join(x for x in (amp.strip(), speed) if x)
    return f"The camera {verb}" + (f" {tail}" if tail else "") + "."


def _size_phrase(text: str) -> str:
    for cn, en in SHOT_SIZE.items():
        if cn in (text or ""):
            return en
    return "a medium shot"


def _sound(text: str, fallback: str = "") -> str:
    t = (text or "").strip() or fallback
    if not t:
        return "N/A"
    return t if t.endswith((".", "。", "!", "！")) else t + "。"


def build(
    action: str,
    *,
    mode: str = "t2va",
    duration: float = 5.0,
    shot_size: str = "",
    camera: str = "",
    dialogue: str = "",
    soundscape: str = "",
    music: str = "",
    style: str = "写实电影感",
    speaker: str = "S1",
    first_frame: bool = False,
) -> str:
    """生成符合 H3 规范的提示词。first_frame=True 表示带首帧图（I2VA）。"""
    head = ""
    if mode == "i2va" or first_frame:
        head = ("For the target video, at 0.00 seconds into the target video, "
                "<Picture 1> (from [Shot 1]) is fully referenced.\n\n")

    parts = [f"[Shot 1] {style}，{_size_phrase(shot_size)}。"]
    if first_frame:
        parts.append("画面以 <Picture 1> 的构图、人物外观、服装与场景为起点，保持上述特征不变，")
    body = (action or "").strip().rstrip("。")
    if body:
        parts.append(body + "。")
    parts.append(_camera_phrase(camera))
    if dialogue.strip():
        parts.append(f'（{speaker}）说：<d>[Chinese] {dialogue.strip()}</d>')

    text = head + "integrated_multimodal_description: " + "".join(parts) + "\n\n"
    text += "overall_soundscape: " + _sound(soundscape, "环境底噪与人物动作声，音量克制") + "\n\n"
    text += "non_diegetic_music: " + (_sound(music) if music.strip() else "N/A")
    return text


def build_multi(shots: list[dict], *, total: float, style: str = "写实电影感") -> str:
    """多镜头版本：按时间轴拼 [Shot n] At mm:ss.SSS。"""
    if not shots:
        return ""
    blocks = []
    t = 0.0
    for i, s in enumerate(shots):
        dur = float(s.get("duration_sec") or s.get("seconds") or 5)
        size = _size_phrase(s.get("shot_size", ""))
        action = (s.get("action") or s.get("prompt") or "").strip().rstrip("。")
        cam = _camera_phrase(s.get("camera", ""))
        dlg = (s.get("dialogue") or "").strip()
        if i == 0:
            piece = f"[Shot 1] {style}，{size}。{action}。{cam}"
        else:
            piece = f"[Shot {i + 1}] At {_ts(t)}, the camera cuts to {size}。{action}。{cam}"
        if dlg:
            piece += f' （S1）说：<d>[Chinese] {dlg}</d>'
        blocks.append(piece)
        t += dur

    sound = "；".join({(s.get("soundscape") or "").strip() for s in shots if (s.get("soundscape") or "").strip()})
    out = "integrated_multimodal_description: " + " ".join(blocks) + "\n\n"
    out += "overall_soundscape: " + _sound(sound, "环境底噪、脚步与衣物摩擦声") + "\n\n"
    out += "non_diegetic_music: " + (_sound(shots[0].get("music", "")) if shots[0].get("music") else "N/A")
    return out


def _ts(seconds: float) -> str:
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m:02d}:{s:06.3f}"


def wrap_i2va(prompt: str, duration: float) -> str:
    return ("For the target video, at 0.00 seconds into the target video, "
            "<Picture 1> (from [Shot 1]) is fully referenced.\n\n" + prompt)


def build_ref(
    action: str,
    subject: str,
    *,
    duration: float = 5.0,
    shot_size: str = "中景",
    camera: str = "",
    dialogue: str = "",
    soundscape: str = "",
    music: str = "",
    style: str = "2D animated TV sitcom, flat vector colors, thick black outlines",
) -> str:
    """Ref2VA：用参考图锁角色，输出官方六段结构。"""
    subj = subject.strip() or "the main character shown in <Picture 1>"
    text = f"subject_definitions: <Subject 1> is the character shown in <Picture 1>: {subj}\n\n"
    text += ("summary: One continuous shot in which <Subject 1> performs a specific action "
             "while keeping the same appearance, clothing and colors as <Picture 1>.\n\n")
    text += ("retention_analysis: <Picture 1> provides the visual identity of <Subject 1> — "
             "face shape, hairstyle, body proportion, clothing colors and outline style are all retained. "
             "No audio is taken from <Picture 1>.\n\n")
    body = (action or "").strip().rstrip("。")
    text += (f"detailed_description: [Shot 1] {style}, {_size_phrase(shot_size)}。"
             f"<Subject 1> keeps the exact appearance of <Picture 1> throughout. {body}。"
             f"{_camera_phrase(camera)}")
    if dialogue.strip():
        text += f' （S1）说：<d>[Chinese] {dialogue.strip()}</d>'
    text += "\n\n"
    text += "overall_soundscape: " + _sound(soundscape, "环境底噪与人物动作声") + "\n\n"
    text += "non_diegetic_music: " + (_sound(music) if music.strip() else "N/A")
    return text
