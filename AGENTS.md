# 给 AI 助手看的安装指引（AGENTS.md）

> 如果你是一个 AI 编程助手（Claude Code / Cursor / OpenClaw / Codex …），
> 用户把本仓库链接丢给你，让你"帮我装好"，请按下面的顺序执行。
> 目标：让画布在本机跑起来，能生成视频。

---

## 0. 先跑体检，别急着动手

```bash
python studio/tools/doctor.py --json
```

返回 JSON：`ready` 为 `true` 就已经能启动了；否则按 `checks` 里 `ok=false` 的项处理。

**每次改动后重跑这一条**，直到 `ready=true`。

---

## 1. 理解项目边界（重要）

| 层 | 是否由你负责 |
|---|---|
| 本仓库代码（Python 标准库 + 前端零依赖） | ✅ 你负责装好、跑通 |
| ComfyUI 本体 + CUDA/torch 环境 | ⚠️ 通常用户已装；你只负责**定位路径**并写进 config.json |
| MiniMax-H3 模型（约 80GB） | ❌ 你**不要**自动下载（体积大、需阅读许可），只输出清单让用户确认 |
| 显卡驱动 | ❌ 不要动 |

端口约定：ComfyUI `8188`，画布 `8770`。

---

## 2. 标准执行顺序

```bash
# ① 体检
python studio/tools/doctor.py --json

# ② 没有 config.json 就从模板复制
cp studio/config.example.json studio/config.json     # Windows: copy

# ③ 编辑 config.json，至少设置：
#    comfy_root  —— 指向含 main.py 的 ComfyUI 目录
#    data_dir    —— 非系统盘，例如 D:/AI-Studio
#    （路径用正斜杠 / 最稳）

# ④ 再看一次体检
python studio/tools/doctor.py

# ⑤ 启动（后台）
python studio/start.py --no-comfy     # 若 ComfyUI 已由用户启动
# 或
python studio/start.py                # 由本项目拉起 ComfyUI

# ⑥ 验证
curl http://127.0.0.1:8770/api/health
# 期望：{"ok": true, "comfy": true, "queue": 0}
```

---

## 3. 找 ComfyUI 路径的规则

`config.json` 的 `comfy_root` 必须指向**含 `main.py` 的那一层**。常见位置：

```
C:/ComfyUI
C:/ComfyUI_windows_portable/ComfyUI
D:/ComfyUI
<用户安装目录>/ComfyUI-Installs/ComfyUI/ComfyUI     # ComfyUI Desktop
```

判断：`<comfy_root>/main.py` 存在。它的 Python 一般是：

```
<comfy_root>/.venv/Scripts/python.exe      # Desktop
<comfy_root>/../python_embeded/python.exe  # Portable
```

找不到就让用户确认，不要猜。

---

## 4. 模型：只输出清单，不自动下载

```bash
python studio/tools/download_models.py --check
```

- `required`（H3 主模型 / 文本编码器 / VAE / LoRA）→ **列出文件名、体积、目标目录和官方地址，让用户自己下**
- `optional`（RealVisXL / IPAdapter）→ 可以代跑：

```bash
python studio/tools/download_models.py --optional --host https://hf-mirror.com
```

模型可以放 `<data_dir>/models/`（推荐，程序会自动挂给 ComfyUI），也可以放 ComfyUI 自己的 `models/`。
体检脚本两处都会找。

---

## 5. 不要做的事

- ❌ 不要修改 ComfyUI 源码
- ❌ 不要把模型 / config.json 提交进 git（`.gitignore` 已处理）
- ❌ 不要擅自填 API Key；用户要用时自己在画布右上角 🔑 填
- ❌ 不要为了"看起来成功"而伪造体检结果

---

## 6. 已知坑（照这个修）

| 现象 | 原因 | 修法 |
|---|---|---|
| `找不到 ComfyUI` | `comfy_root` 指错层 | 必须含 `main.py` |
| 画布 `comfy: false` | ComfyUI 没起 / 端口不是 8188 | 先 `curl http://127.0.0.1:8188/queue` 验证 |
| ComfyUI 启动报 `nvml_pressure` | 它的 `comfy_aimdo` 比 main.py 旧 | 用 `studio/tools/start_comfy.py` 启动（带兼容层） |
| ComfyUI 启动报 `newbyteorder` | numpy 2.x 移除该 API | 同上，兼容层已补 |
| 生成报 OOM | 显存不足 | 用 `preset: "draft"`（360P/4步），缩短秒数 |
| 模型目录放对了但 ComfyUI 看不到 | 没有挂 extra paths | 用本项目启动会自动生成并挂载 `extra_model_paths.yaml` |

---

## 7. 完成标准

```
python studio/tools/doctor.py  →  全部 [OK]，最后一行「可以启动」
curl /api/health              →  {"ok": true, "comfy": true}
提交一个 2 秒草稿镜头能出 mp4 →
   POST /api/render {"prompt":"a cat","seconds":2,"preset":"draft"}
```

三条都过了，才算装好。

---

## 8. 给用户的最终话术

装好后告诉用户：

1. 画布地址：<http://127.0.0.1:8770>
2. 启动方式：双击 `studio/start.bat`
3. 想要真编剧：右上角 🔑 填 OpenAI 兼容的 API Key（可选，不填也能用模板）
4. 角色一致性怎么保证：看 `docs/CHARACTER-CONSISTENCY.md`
