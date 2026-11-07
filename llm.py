"""统一的 OpenAI 兼容调用层。

任何提供 /chat/completions 的服务都能接：DeepSeek、OpenAI、Kimi、智谱、
通义（compatible-mode）、硅基流动、OpenRouter、本地 Ollama / vLLM …

不同服务对 response_format 的支持不一致，这里做三级降级：
  1. 带 response_format={"type":"json_object"}
  2. 去掉 response_format，仅靠提示词要求 JSON
  3. 从返回文本里用括号匹配抠出 JSON
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request


HINTS = {
    400: "请求格式被拒绝（可能是模型名不存在，或该服务不支持当前参数）",
    401: "API Key 无效或已失效 —— 去服务商后台重新生成一个（注意别把旧 key 贴回来）",
    402: "账户余额不足 —— 去后台充值",
    403: "没有权限 —— key 可能没开通该模型，或被盗用后被限制",
    404: "接口地址不对 —— 检查 Base URL（DeepSeek 用 https://api.deepseek.com，OpenAI 要带 /v1）",
    429: "请求太频繁 / 限流 —— 等一会儿再试",
    500: "服务端错误 —— 稍后重试",
    503: "模型服务繁忙 —— 稍后重试",
}


def _post(url: str, key: str, payload: dict, timeout: int = 180) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            raw = e.read().decode("utf-8", "ignore")
            try:
                j = json.loads(raw)
                detail = (j.get("error") or {}).get("message") or raw
            except Exception:
                detail = raw
        except Exception:
            pass
        hint = HINTS.get(e.code, "")
        parts = [f"HTTP {e.code}"]
        if hint:
            parts.append(hint)
        if detail:
            parts.append(detail.strip()[:200])
        raise RuntimeError("；".join(parts)) from None


def _extract_json(text: str) -> dict:
    """从可能夹着解释文字的回复里抠出第一个完整 JSON 对象。"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    if start < 0:
        raise ValueError("回复里没有 JSON")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("JSON 不完整")


def complete(cfg: dict, messages: list[dict], *, json_mode: bool = True,
             timeout: int = 180) -> dict:
    base = (cfg.get("base_url") or "https://api.deepseek.com").rstrip("/")
    url = base + "/chat/completions"
    key = cfg.get("api_key") or ""
    payload = {
        "model": cfg.get("model") or "deepseek-chat",
        "messages": messages,
        "temperature": cfg.get("temperature", 0.8),
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        data = _post(url, key, payload, timeout)
    except urllib.error.HTTPError as e:
        if e.code not in (400, 422):
            raise
        # 有些服务不认 response_format，去掉再试
        payload.pop("response_format", None)
        data = _post(url, key, payload, timeout)

    content = data["choices"][0]["message"]["content"]
    if not json_mode:
        return {"text": content, "raw": data}
    return {"data": _extract_json(content), "text": content, "raw": data}
