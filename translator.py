"""中文提示词 → 英文（SDXL 的 CLIP 读不懂中文）。

有 config.json 的 api_key 时用 LLM 翻译；没有就原样返回，并在结果里标注
`translated: false`，让前端提示用户写英文。
"""
from __future__ import annotations

import json
import re
import urllib.request

import llm
from llm import complete as llm_complete
from director import load_cfg

CJK = re.compile(r"[\u4e00-\u9fff]")
_cache: dict[str, str] = {}

SYS = ("Translate the user's Chinese image prompt into concise English SDXL prompt tags. "
       "Keep it under 60 words, comma separated, no explanations, no quotes. "
       "Preserve character details, clothing, lighting, camera and mood.")


def to_en(text: str, llm: dict | None = None) -> tuple[str, bool]:
    if not CJK.search(text):
        return text, True
    if text in _cache:
        return _cache[text], True
    cfg = llm if (llm and llm.get("api_key")) else load_cfg()
    if not cfg.get("api_key"):
        return text, False
    try:
        out = llm_complete(cfg, [{"role": "system", "content": SYS},
                                 {"role": "user", "content": text}],
                           json_mode=False, timeout=60)["text"].strip().strip('"')
        _cache[text] = out
        return out, True
    except Exception:
        return text, False
