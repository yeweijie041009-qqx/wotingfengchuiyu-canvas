"""Skill 加载器：把 .skill 包（SKILL.md + references/）读成可用的提示词。

目录约定：studio/skills/<skill-name>/SKILL.md + references/*.md
"""
from __future__ import annotations

import os
import sys
import re

SKILLS_DIR = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "skills")


def list_skills() -> list[dict]:
    """扫描 skills/ 下所有含 SKILL.md 的目录（支持多级，如 minimax-h3/h3-prompt-writing）。"""
    out = []
    if not os.path.isdir(SKILLS_DIR):
        return out
    for root, dirs, files in os.walk(SKILLS_DIR):
        dirs[:] = [x for x in dirs if not x.startswith(".")]
        if "SKILL.md" not in files:
            continue
        name = os.path.relpath(root, SKILLS_DIR).replace("\\", "/")
        found, total = [], 0
        for r2, _d2, f2 in os.walk(root):
            for f in f2:
                if not f.endswith(".md"):
                    continue
                p = os.path.join(r2, f)
                rel = os.path.relpath(p, root).replace("\\", "/")
                size = os.path.getsize(p)
                total += size
                found.append({"file": rel, "bytes": size})
        meta = read_meta(os.path.join(root, "SKILL.md"))
        out.append({"name": name, "description": meta.get("description", ""),
                    "files": found, "total_bytes": total})
    out.sort(key=lambda x: x["name"])
    return out


def read_meta(skill_md_path: str) -> dict:
    """读 SKILL.md 顶部的 YAML front matter（只取 name / description）。"""
    try:
        with open(skill_md_path, encoding="utf-8") as f:
            text = f.read(4000)
    except OSError:
        return {}
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().lstrip(">").strip()
    return meta


def read_file(skill: str, rel: str) -> str:
    p = os.path.normpath(os.path.join(SKILLS_DIR, skill, rel))
    if not p.startswith(os.path.join(SKILLS_DIR, skill)) or not os.path.isfile(p):
        raise FileNotFoundError(rel)
    with open(p, encoding="utf-8") as f:
        return f.read()


def compose(skill: str, refs: list[str], max_chars: int = 120_000) -> str:
    """把 SKILL.md 和指定参考资料拼成 system prompt。"""
    parts = [read_file(skill, "SKILL.md")]
    for r in refs:
        try:
            body = read_file(skill, r)
        except FileNotFoundError:
            continue
        if sum(len(p) for p in parts) + len(body) > max_chars:
            body = body[: max_chars - sum(len(p) for p in parts)]
        parts.append(f"\n\n<!-- ===== {r} ===== -->\n\n{body}")
    return "".join(parts)
