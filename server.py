"""AI 短剧画布 · 本地后端（仅标准库）

职责：
  1. 提供前端静态文件
  2. 把画布上的"视频节点"变成 MiniMax-H3 渲染任务（单卡串行队列）
  3. 代理 ComfyUI 的输出文件
  4. 保存/读取画布工程
  5. 给 Agent 用的同一套 HTTP API

启动：python server.py  → http://127.0.0.1:8770
"""
from __future__ import annotations

import json
import mimetypes
import os
import queue
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import director
import h3
import h3_prompt
import imaging
import llm
import paths
import screenwriter
import skills_loader
import translator

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")
PROJECTS = os.path.join(ROOT, "projects")
os.makedirs(PROJECTS, exist_ok=True)

JOBS: dict[str, dict] = {}
JOB_Q: "queue.Queue[str]" = queue.Queue()
LOCK = threading.Lock()
GPU = threading.Lock()          # 一张卡，串行
AGENTS: dict[str, dict] = {}
OUT_DIR = paths.OUTPUT
IN_DIR = paths.INPUT
VENV_PY = paths.COMFY_PY
paths.ensure_dirs()


def _worker():
    while True:
        job_id = JOB_Q.get()
        job = JOBS.get(job_id)
        if not job:
            continue
        job.update(status="running", started=time.time())
        try:
            if job.get("kind") == "image":
                engine = (job.get("engine") or "sdxl").lower()
                ref = _stage_image(job.get("ref"))
                if engine == "i2i" and ref:
                    graph = imaging.build_i2i(
                        job["prompt"], ref,
                        aspect=job.get("aspect", "9:16"),
                        steps=int(job.get("steps", 30)),
                        denoise=float(job.get("denoise", 0.5)),
                        seed=int(job.get("seed", 0)),
                        prefix=f"i2i_{job['id']}",
                    )
                    text, ok = job["prompt"], True
                else:
                    text, ok = translator.to_en(job["prompt"], job.get("llm"))
                    graph = imaging.build(
                        text,
                        mode=job.get("mode", "single"),
                        aspect=job.get("aspect", "9:16"),
                        width=job.get("width"),
                        height=job.get("height"),
                        steps=int(job.get("steps", 28)),
                        seed=int(job.get("seed", 0)),
                        prefix=f"img_{job['id']}",
                        ref_image=ref,
                        ip_weight=float(job.get("ip_weight", 0.6)),
                        ckpt=job.get("ckpt") or None,
                    )
            else:
                m = h3.models()
                res, steps, lora = h3.resolve_preset(job.get("preset", "standard"), m)
                if job.get("resolution"):
                    res = job["resolution"]
                if job.get("steps"):
                    steps = int(job["steps"])
                vid_mode = "ref2va" if (job.get("ref_mode") and job.get("image")) else job.get("mode", "t2va")
                vid_prompt = job["prompt"]
                if vid_mode == "ref2va":
                    vid_prompt = h3_prompt.build_ref(
                        job["prompt"], job.get("subject", ""),
                        duration=float(job.get("seconds", 5)),
                        shot_size=job.get("shot_size", "中景"),
                        camera=job.get("camera", ""),
                        dialogue=job.get("dialogue", ""),
                        soundscape=job.get("soundscape", ""),
                    )
                graph = h3.build_graph(
                    vid_prompt,
                    mode=vid_mode,
                    resolution=res,
                    aspect=job.get("aspect", "9:16"),
                    width=int(job.get("width", 720)),
                    height=int(job.get("height", 1280)),
                    seconds=float(job.get("seconds", 5)),
                    fps=float(job.get("fps", 24)),
                    seed=int(job.get("seed", 0)),
                    steps=steps,
                    lora=lora,
                    use_turbo=bool(job.get("turbo", True)),
                    image=_stage_image(job.get("image")),
                    m=m,
                )
            with GPU:
                pid = h3.submit(graph)
                job["comfy_prompt_id"] = pid
                result = h3.wait(pid, poll=3.0)
            files = h3.files_from(result)
            job.update(
                status="done",
                elapsed=result["elapsed"],
                files=files,
                finished=time.time(),
                prompt_en=text if job.get("kind") == "image" else None,
                translated=ok if job.get("kind") == "image" else None,
            )
        except Exception as e:  # noqa: BLE001
            job.update(status="error", error=str(e)[:4000], finished=time.time())
        finally:
            JOB_Q.task_done()


threading.Thread(target=_worker, daemon=True).start()


def run_agent(job_id: str):
    """一句话 → 分镜 → 逐镜渲染 → 拼成片。"""
    job = AGENTS[job_id]
    t0 = time.time()
    try:
        job["stage"] = "story"
        if job.get("use_skill"):
            sp = screenwriter.plan(job["idea"], job.get("format", "ultrashort"),
                                   int(job.get("shots", 5)),
                                   float(job.get("seconds", 5)),
                                   job.get("style", "电影感写实风格"),
                                   llm=job.get("llm"))
            sb = sp["storyboard"]
            job["plan"] = {"title": sb.get("title", ""), "logline": sb.get("logline", ""),
                           "provider": sp["provider"], "note": sp.get("note", "")}
            job["items"] = [{"index": s["index"], "beat": s.get("beat", ""),
                             "prompt": s.get("h3_prompt") or s.get("action", ""),
                             "seconds": s.get("duration_sec", 5),
                             "status": "queued", "file": None}
                            for s in sb["shots"]]
        else:
            p = director.plan(job["idea"], int(job.get("shots", 5)),
                              job.get("style", "电影感写实风格"),
                              float(job.get("seconds", 5)),
                              llm=job.get("llm"))
            job["plan"] = {"title": p["title"], "logline": p["logline"],
                           "provider": p["provider"], "note": p.get("note")}
            job["items"] = [{"index": s["index"], "beat": s["beat"], "prompt": s["prompt"],
                             "seconds": s["seconds"], "status": "queued", "file": None}
                            for s in p["shots"]]
        job["stage"] = "render"
        m = h3.models()
        res, steps, lora = h3.resolve_preset(job.get("preset", "standard"), m)
        for it in job["items"]:
            it["status"] = "running"
            it["t0"] = time.time()
            try:
                shot_prompt = it["prompt"]
                ref_mode = bool(job.get("ref_mode"))
                if job.get("h3_prompt", True) and not ref_mode and "integrated_multimodal_description" not in shot_prompt:
                    # 按 MiniMax-H3 官方提示词规范重写这一镜
                    shot_prompt = h3_prompt.build(
                        it["prompt"],
                        mode="t2va",
                        duration=float(it["seconds"]),
                        soundscape=it.get("soundscape", ""),
                        style=job.get("style", "写实电影感"),
                    )
                graph = h3.build_graph(
                    shot_prompt,
                    resolution=res,
                    aspect=job.get("aspect", "9:16"),
                    width=int(job.get("width", 480)),
                    height=int(job.get("height", 864)),
                    seconds=float(it["seconds"]),
                    seed=int(job.get("seed", 0)) + it["index"] * 977,
                    steps=steps,
                    lora=lora,
                    prefix=f"agent{job_id}_{it['index']:02d}",
                    m=m,
                )
                with GPU:
                    pid = h3.submit(graph)
                    result = h3.wait(pid, poll=3.0)
                files = h3.files_from(result)
                it["file"] = files[0] if files else None
                it["status"] = "done" if it["file"] else "error"
                it["elapsed"] = result["elapsed"]
            except Exception as e:  # noqa: BLE001
                it["status"] = "error"
                it["error"] = str(e)[:800]
            it.pop("t0", None)

        done = [it for it in job["items"] if it.get("file")]
        job["stage"] = "concat"
        if len(done) >= 2:
            final = f"film_{job_id}.mp4"
            paths = [os.path.join(OUT_DIR, it["file"]["filename"]) for it in done]
            try:
                r = subprocess.run(
                    [VENV_PY, os.path.join(ROOT, "tools", "concat.py"),
                     os.path.join(OUT_DIR, final)] + paths,
                    capture_output=True, text=True, timeout=1800)
                if r.returncode == 0:
                    job["final"] = {"filename": final, "subfolder": "", "type": "output"}
                else:
                    job["concat_error"] = (r.stderr or r.stdout)[-800:]
            except Exception as e:  # noqa: BLE001
                job["concat_error"] = str(e)[:800]
        job["stage"] = "done"
    except Exception as e:  # noqa: BLE001
        job.update(stage="error", error=str(e)[:2000])
    finally:
        job["elapsed"] = round(time.time() - t0, 1)


def _stage_image(name: str | None) -> str | None:
    """把 output 里的图复制到 ComfyUI 的 input 目录，供 LoadImage 使用（首帧生视频）。"""
    if not name:
        return None
    src = os.path.join(OUT_DIR, name)
    if not os.path.isfile(src):
        return None
    dst = os.path.join(IN_DIR, name)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not os.path.isfile(dst):
        import shutil
        shutil.copyfile(src, dst)
    return name


def _beats(text: str, n: int) -> list[str]:
    """不做碎片化拆句——碎片会让 SDXL 跑偏。整段复用，只标注镜头序号。"""
    return [f"{text}, storyboard frame {i + 1} of {n}, consistent character and location"
            for i in range(n)]


def run_storyboard(job_id: str):
    """多张独立分镜图 + 拼成宫格联络表。"""
    job = JOBS[job_id]
    t0 = time.time()
    try:
        n = int(job.get("panels", 4))
        cols = 2 if n == 4 else 3
        rows = n // cols
        base, _ok = translator.to_en(job["prompt"])
        beats = _beats(base, n)
        files = []
        for i, b in enumerate(beats):
            graph = imaging.build(
                b, mode="single", aspect=job.get("aspect", "16:9"),
                steps=int(job.get("steps", 28)),
                seed=int(job.get("seed", 0)) + i * 131,
                prefix=f"panel_{job_id}_{i + 1}",
            )
            with GPU:
                pid = h3.submit(graph)
                res = h3.wait(pid, poll=2.0)
            got = h3.files_from(res)
            if got:
                files.append(got[0])
            job["progress"] = {"done": i + 1, "total": n}
        if len(files) < n:
            raise RuntimeError(f"只成功 {len(files)}/{n} 张")
        board = f"board_{job_id}.png"
        r = subprocess.run(
            [VENV_PY, os.path.join(ROOT, "tools", "tile_grid.py"),
             os.path.join(OUT_DIR, board), str(rows), str(cols)]
            + [os.path.join(OUT_DIR, f["filename"]) for f in files],
            capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout)[-500:])
        job["files"] = [{"filename": board, "subfolder": "", "type": "output",
                         "metadata": {"kind": "image"}}] + files
        job["status"] = "done"
    except Exception as e:  # noqa: BLE001
        job.update(status="error", error=str(e)[:1500])
    finally:
        job["elapsed"] = round(time.time() - t0, 1)
        job["finished"] = time.time()


def start_agent(payload: dict) -> str:
    job_id = uuid.uuid4().hex[:10]
    job = {
        "id": job_id, "idea": payload.get("idea", "").strip(),
        "shots": int(payload.get("shots", 5)),
        "preset": payload.get("preset", "standard"),
        "resolution": payload.get("resolution", ""),
        "aspect": payload.get("aspect", "9:16"),
        "style": payload.get("style", "电影感写实风格"),
        "use_skill": bool(payload.get("use_skill", False)),
        "llm": payload.get("llm") or None,
        "format": payload.get("format", "ultrashort"),
        "stage": "queued", "items": [], "final": None, "created": time.time(),
    }
    AGENTS[job_id] = job
    threading.Thread(target=run_agent, args=(job_id,), daemon=True).start()
    return job_id


class Handler(BaseHTTPRequestHandler):
    server_version = "AIStudio/0.1"

    # ---------- helpers ----------
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def _static(self, path):
        if path == "/" or path == "":
            path = "/index.html"
        full = os.path.normpath(os.path.join(WEB, path.lstrip("/")))
        if not full.startswith(WEB) or not os.path.isfile(full):
            self.send_error(404, "not found")
            return
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") else ""))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---------- routes ----------
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        p = u.path
        q = urllib.parse.parse_qs(u.query)
        try:
            if p == "/api/health":
                return self._json({"ok": True, "comfy": h3.alive(), "queue": JOB_Q.qsize()})
            if p == "/api/presets":
                return self._json({"presets": [dict(key=k, **v) for k, v in h3.PRESETS.items()]})
            if p == "/api/skills":
                return self._json({"skills": skills_loader.list_skills(),
                                   "formats": screenwriter.FORMATS})
            if p == "/api/skills/file":
                name = (q.get("name") or ["screenwriting-master"])[0]
                rel = (q.get("file") or ["SKILL.md"])[0]
                try:
                    text = skills_loader.read_file(name, rel)
                except FileNotFoundError:
                    return self._json({"error": "no such file"}, 404)
                return self._json({"name": name, "file": rel, "chars": len(text), "text": text})
            if p == "/api/models":
                if not h3.alive():
                    return self._json({"error": "ComfyUI 未启动"}, 503)
                return self._json(h3.models().as_dict())
            if p.startswith("/api/agent/job/"):
                job = AGENTS.get(p.rsplit("/", 1)[-1])
                return self._json(job or {"error": "no such job"}, 200 if job else 404)
            if p == "/api/jobs":
                with LOCK:
                    return self._json(list(JOBS.values())[-50:])
            if p.startswith("/api/job/"):
                job = JOBS.get(p.rsplit("/", 1)[-1])
                return self._json(job or {"error": "no such job"}, 200 if job else 404)
            if p == "/api/media":
                return self._media(q)
            if p == "/api/project":
                name = (q.get("name") or ["current"])[0]
                fp = os.path.join(PROJECTS, name + ".json")
                if not os.path.isfile(fp):
                    return self._json({"nodes": [], "edges": []})
                with open(fp, encoding="utf-8") as f:
                    return self._json(json.load(f))
            if p.startswith("/api/"):
                return self._json({"error": "unknown endpoint"}, 404)
            return self._static(p)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": str(e)}, 500)

    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        try:
            body = self._read_json()
            if p == "/api/image/render":
                if not (body.get("prompt") or "").strip():
                    return self._json({"error": "prompt 不能为空"}, 400)
                if not h3.alive():
                    return self._json({"error": "ComfyUI 未启动"}, 503)
                if not imaging.pick_checkpoint():
                    return self._json({"error": "还没装图像模型（见 docs/PLAN.md 的 M-A）"}, 409)
                job_id = uuid.uuid4().hex[:12]
                body.update(id=job_id, kind="image", status="queued", created=time.time())
                with LOCK:
                    JOBS[job_id] = body
                JOB_Q.put(job_id)
                return self._json({"id": job_id, "ahead": JOB_Q.qsize() - 1})
            if p == "/api/image/storyboard":
                if not (body.get("prompt") or "").strip():
                    return self._json({"error": "prompt 不能为空"}, 400)
                if not h3.alive():
                    return self._json({"error": "ComfyUI 未启动"}, 503)
                if not imaging.pick_checkpoint():
                    return self._json({"error": "还没装图像模型"}, 409)
                job_id = uuid.uuid4().hex[:12]
                body.update(id=job_id, kind="storyboard", status="running", created=time.time())
                with LOCK:
                    JOBS[job_id] = body
                threading.Thread(target=run_storyboard, args=(job_id,), daemon=True).start()
                return self._json({"id": job_id})
            if p == "/api/image/slice":
                filename = body.get("filename") or ""
                rows, cols = int(body.get("rows", 3)), int(body.get("cols", 3))
                if not filename:
                    return self._json({"error": "filename 不能为空"}, 400)
                sub = "slices_" + os.path.splitext(filename)[0]
                outdir = os.path.join(OUT_DIR, sub)
                r = subprocess.run(
                    [VENV_PY, os.path.join(ROOT, "tools", "slice_grid.py"),
                     os.path.join(OUT_DIR, filename), outdir, str(rows), str(cols), "panel"],
                    capture_output=True, text=True, timeout=300)
                if r.returncode != 0:
                    return self._json({"error": (r.stderr or r.stdout)[-800:]}, 500)
                data = json.loads(r.stdout.strip().splitlines()[-1])
                for f in data["files"]:
                    f["subfolder"] = sub
                return self._json(data)
            if p == "/api/render":
                if not body.get("prompt"):
                    return self._json({"error": "prompt 不能为空"}, 400)
                job_id = uuid.uuid4().hex[:12]
                body.update(id=job_id, status="queued", created=time.time())
                with LOCK:
                    JOBS[job_id] = body
                JOB_Q.put(job_id)
                return self._json({"id": job_id, "ahead": JOB_Q.qsize() - 1})
            if p == "/api/agent/start":
                if not (body.get("idea") or "").strip():
                    return self._json({"error": "idea 不能为空"}, 400)
                if not h3.alive():
                    return self._json({"error": "ComfyUI 未启动"}, 503)
                return self._json({"id": start_agent(body)})
            if p == "/api/llm/test":
                cfg = body.get("llm") or {}
                if not cfg.get("api_key"):
                    return self._json({"ok": False, "error": "没有 api_key"}, 400)
                try:
                    r = llm.complete(cfg, [{"role": "user", "content": "只回复两个字：可用"}],
                                     json_mode=False, timeout=40)
                    return self._json({"ok": True, "model": cfg.get("model"),
                                       "reply": r["text"][:40]})
                except Exception as e:  # noqa: BLE001
                    return self._json({"ok": False, "error": f"{type(e).__name__}: {e}"[:400]}, 200)
            if p == "/api/prompt/h3":
                prompt = h3_prompt.build(
                    body.get("action", body.get("prompt", "")),
                    mode=body.get("mode", "t2va"),
                    duration=float(body.get("duration", 5)),
                    shot_size=body.get("shot_size", ""),
                    camera=body.get("camera", ""),
                    dialogue=body.get("dialogue", ""),
                    soundscape=body.get("soundscape", ""),
                    music=body.get("music", ""),
                    style=body.get("style", "写实电影感"),
                    first_frame=bool(body.get("first_frame", False)),
                ) if not body.get("multi") else h3_prompt.build_multi(
                    body.get("multi", []), total=float(body.get("duration", 5)),
                    style=body.get("style", "写实电影感"))
                return self._json({"prompt": prompt})
            if p == "/api/director/outline":
                if not (body.get("idea") or "").strip():
                    return self._json({"error": "idea 不能为空"}, 400)
                return self._json(screenwriter.outline(
                    body["idea"], body.get("format", "series"),
                    int(body.get("units", 4)),
                    llm_cfg=body.get("llm"),
                    minutes_per_unit=float(body.get("minutes", 3)),
                ))
            if p == "/api/director/expand":
                if not body.get("unit"):
                    return self._json({"error": "缺少 unit"}, 400)
                return self._json(screenwriter.expand(
                    body.get("idea", ""), body["unit"],
                    shots=int(body.get("shots", 6)),
                    seconds=float(body.get("seconds", 5)),
                    style=body.get("style", "电影感写实风格"),
                    llm_cfg=body.get("llm"),
                    fmt=body.get("format", "series"),
                ))
            if p == "/api/director/script":
                if not (body.get("idea") or "").strip():
                    return self._json({"error": "idea 不能为空"}, 400)
                return self._json(screenwriter.plan(
                    body["idea"],
                    body.get("format", "ultrashort"),
                    int(body.get("shots", 6)),
                    float(body.get("seconds", 5)),
                    body.get("style", "电影感写实风格"),
                    llm=body.get("llm"),
                ))
            if p == "/api/director/to_agent":
                if not (body.get("idea") or "").strip():
                    return self._json({"error": "idea 不能为空"}, 400)
                if not h3.alive():
                    return self._json({"error": "ComfyUI 未启动"}, 503)
                body["use_skill"] = True
                return self._json({"id": start_agent(body)})
            if p == "/api/project":
                name = body.get("name") or "current"
                fp = os.path.join(PROJECTS, name + ".json")
                with open(fp, "w", encoding="utf-8") as f:
                    json.dump({k: v for k, v in body.items() if k != "name"}, f, ensure_ascii=False, indent=2)
                return self._json({"ok": True, "path": fp})
            return self._json({"error": "unknown endpoint"}, 404)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": str(e)}, 500)

    def _media(self, q):
        filename = (q.get("filename") or [""])[0]
        subfolder = (q.get("subfolder") or [""])[0]
        url = "http://127.0.0.1:8188/view?" + urllib.parse.urlencode(
            {"filename": filename, "subfolder": subfolder, "type": "output"})
        with urllib.request.urlopen(url, timeout=120) as r:
            data = r.read()
            ctype = r.headers.get("Content-Type", "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print("[%s] %s" % (time.strftime("%H:%M:%S"), fmt % args), flush=True)


def main():
    port = paths.PORT
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"AI 短剧画布 → http://127.0.0.1:{port}   (ComfyUI: {h3.COMFY})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
