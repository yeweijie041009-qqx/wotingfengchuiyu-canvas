# 卧听风吹雨 · 无限画布

> 「夜阑卧听风吹雨」· 一块无限画布，把 **导演 → 剧本 → 分镜图 → 视频 → 成片** 串成一条链。
> 视频与图片生成全部跑在**你自己电脑上的 ComfyUI**，不依赖任何云端生成服务；
> 模型**可插拔**——想用哪个自己下、自己配。

> **第一次装 → 看 [`说明书.md`](说明书.md)**（含模型清单与常见问题）
> **想让 AI 帮你装 → 把仓库链接丢给 Claude / Cursor / OpenClaw，它会自动读到 [`AGENTS.md`](AGENTS.md)**
> **做角色一致的片子 → 看 [`docs/CHARACTER-CONSISTENCY.md`](docs/CHARACTER-CONSISTENCY.md)**
> **加自己的模型 → 看 [`profiles/README.md`](profiles/README.md)**

---

## 它是什么

| 能力 | 说明 |
|---|---|
| **无限画布 + 节点** | 导演 / 图片 / 视频 / 文本，可连线、可复制、可删（右键 / Delete / Enter） |
| **导演节点** | 接「山音超级编剧大师」skill；超短片 / 短片 / 长片 / 剧集四种格式；长片剧集走「大纲 → 按集展开」；剧本可视化、可逐镜改词 |
| **视频节点** | 文生视频 / 首帧生视频 / **参考图锁角色**；带音效与对白；草稿 360P / 标准 480P | 
| **图片节点** | 单图 / 角色三视图 / 四宫格 / 九宫格 / 通用「切 N 行 M 列」；可存为主体、可一键转视频 |
| **模型可插拔** | 一份 `profiles/*.json` = 一个模型。H3、SDXL 是内置的，加 Flux / Wan / LTX 只需加一个 JSON，不改代码 |
| **H3 提示词规范** | 按 MiniMax 官方 `h3-prompt-writing` skill 自动组装三段 / 六段结构（镜头运动、说话人 ID、台词标签） |
| **一句话成片** | 输入一句话 → 分镜 → 逐镜渲染 → 自动拼接（CFR 24fps，带音轨） |
| **LLM 可选** | 不填 Key 也能用（模板分镜）；填了才真正驱动编剧 skill。支持 DeepSeek / OpenAI / Kimi / 智谱 / 通义 / 硅基流动 / OpenRouter / 本地 Ollama |

---

## 前置条件

- **Windows + NVIDIA 显卡**（验证环境：RTX 4060 Laptop 8GB 显存 / 16GB 内存）
- **ComfyUI**（0.42.x）已装好，且装有所需模型的节点包
- **Python 3.10+**（画布后端只用标准库，零依赖）

8GB 显存能跑 480P/8 步（5 秒镜头约 5 分钟）；16GB 内存是硬下限。

---

## 快速开始

```bash
git clone https://github.com/yeweijie041009-qqx/wotingfengchuiyu-canvas.git
cd wotingfengchuiyu-canvas/studio

copy config.example.json config.json     # 改 comfy_root 和 data_dir
python tools\doctor.py                   # 体检，全 [OK] 再继续
start.bat                                # 起 ComfyUI + 画布 + 开浏览器
```

打开 <http://127.0.0.1:8770>。

**更省事的启动方式**

| 方式 | 说明 |
|---|---|
| `启动.vbs` | 双击，无黑窗口，已在运行则只开浏览器 |
| `start.bat` | 有控制台输出，便于看报错 |
| `打包EXE.bat` | 打包成 `dist/wotingfengchuiyu.exe`（需先装 PyInstaller） |

> exe 只是启动器，**ComfyUI 与模型仍需安装**（模型约 80GB，无法打包）。

`config.json` 最少改两项：

```json
{
  "data_dir": "D:/AI-Studio",
  "comfy_root": "E:/ComfyUI",
  "port": 8770
}
```

`data_dir` 首次启动会自动建 `models/ output/ input/ temp/`，并通过自动生成的
`extra_model_paths.yaml` 挂给 ComfyUI —— **不改动 ComfyUI 原安装**。

---

## 模型可插拔（核心设计）

```
画布 / 节点 / 剧本 / 成片        ← 产品层，代码约 1MB
        ↓
profiles/*.json                ← 模型档案：换模型只加一个 JSON
        ↓
ComfyUI（推理运行时）           ← 对用户透明
        ↓
任意模型：H3 / SDXL / Flux / Wan / LTX …
```

内置两个档案：

| 档案 | 类型 | 用途 |
|---|---|---|
| `h3-video` | video | 文生 / 首帧 / 参考图锁角色，自带音效对白 |
| `sdxl-image` | image | 文生图，可换任意 SDXL 底模 |

加自己的模型：

```jsonc
// studio/profiles/flux-image.json
{
  "id": "flux-image", "name": "Flux.1 dev", "kind": "image",
  "requires": [{"dir": "diffusion_models", "file": "flux1-dev.safetensors"}],
  "params": {
    "prompt": {"node": "6", "input": "text"},
    "seed":   {"node": "7", "input": "seed", "type": "int"}
  },
  "graph": { /* ComfyUI 导出的 API 格式工作流 */ }
}
```

重启后，画布对应节点的「模型」下拉里就会出现它。缺模型时会标「（缺模型）」。
详见 [`profiles/README.md`](profiles/README.md)。

---

## 目录结构

```
studio/
  server.py            后端：静态文件 / 任务队列 / 媒体代理 / 工程存档
  launcher.py          exe / 直启入口
  paths.py             路径解析（环境变量 > config.json > 自动探测）
  profiles.py          模型档案加载与图构建
  h3.py                ComfyUI 客户端 + H3 计算图
  h3_prompt.py         H3 官方提示词规范（T2VA / I2VA / Ref2VA）
  imaging.py           SDXL 出图 / 宫格 / 图生图 / IPAdapter
  screenwriter.py      编剧 skill 调度（大纲 / 展开 / 分镜）
  director.py          轻量分镜（不接 LLM 时的兜底）
  llm.py               OpenAI 兼容层（多服务商 + JSON 降级 + 中文报错）
  profiles/            模型档案（h3-video / sdxl-image）
  skills/              内置 skill（山音编剧 + MiniMax 官方 9 个）
  web/                 画布前端（零依赖、无构建）
  tools/               doctor / 下载 / 拼接 / 切分 / 打包
  docs/                SOP 与安装文档

<data_dir>/
  models/  output/  input/  temp/
```

---

## HTTP API（也是 Agent 入口）

```bash
# 模型档案
GET  /api/profiles

# 一条龙：一句话 → 分镜 → 渲染 → 拼接
POST /api/agent/start   {"idea":"...", "shots":6, "preset":"draft", "use_skill":true, "format":"ultrashort"}
GET  /api/agent/job/<id>

# 只出剧本 / 长片剧集
POST /api/director/script    {"idea":"...", "format":"ultrashort", "shots":6}
POST /api/director/outline   {"idea":"...", "format":"series", "units":6, "minutes":3}
POST /api/director/expand    {"idea":"...", "unit":{...}, "shots":6}

# 单镜头（可带首帧 / 参考图 / 指定模型档案）
POST /api/render  {"prompt":"...", "seconds":5, "preset":"standard",
                   "profile":"h3-video", "image":"a.png", "ref_mode":true}

# 出图（可指定图片档案）
POST /api/image/render  {"prompt":"...", "engine":"sdxl", "profile":"sdxl-image", "aspect":"16:9"}

# 按 H3 规范生成提示词
POST /api/prompt/h3  {"action":"...", "duration":5, "shot_size":"中景", "camera":"缓慢推近", "dialogue":"..."}

# skill
GET  /api/skills
GET  /api/skills/file?name=screenwriting-master&file=SKILL.md
```

> 任何请求都可带 `"llm": {"api_key":"...", "base_url":"...", "model":"..."}` 临时指定模型；
> 不带就用 `config.json` 的，或走纯模板模式。

---

## 模型清单

| 模型 | 大小 | 用途 | 必需 |
|---|---|---|---|
| MiniMax-H3 fl2va / ref2va / 文本编码器 / VAE / turbo LoRA | ~80GB | 视频生成 | 视频功能必需 |
| RealVisXL V5（或任意 SDXL 底模） | 6.5GB | 出图 / 角色设定表 | 图片功能必需 |
| ip-adapter-plus + CLIP-ViT-H | 3.1GB | 参考图引导 | 可选 |

```bash
python tools/download_models.py --check      # 看缺什么
python tools/download_models.py --optional   # 自动下可选的图片模型
```

---

## 已知限制

- **单卡串行**：一次一个镜头，队列执行
- **动作控制弱**：Ref2VA 能锁人和场景，精细表演做不出来（见 SOP）
- **口型不对位**：台词是模型生成的对白音轨
- **两人对手戏**：一张参考图只能锁一个角色
- **8GB / 16GB 是下限**，再低会 OOM

---

## 第三方组件与许可

见 [`NOTICE.md`](NOTICE.md)。要点：

- **MiniMax-H3** 模型与官方 skills 版权归 MiniMax
- **山音超级编剧大师**：MIT，作者 @山音，保留原始署名
- **ComfyUI**：GPL-3.0，本项目只调 HTTP API，不改源码
- 本仓库代码：MIT（见 [`LICENSE`](LICENSE)）

生成内容的版权与合规（尤其涉及知名 IP 的“风格模仿”）由使用者自行负责。
