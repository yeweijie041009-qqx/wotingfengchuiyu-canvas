# 卧听风吹雨 · 无限画布（本地 MiniMax-H3）

> 「夜阑卧听风吹雨」· 无限画布 AI 短剧工作台
> 一块可以无限平移缩放的画布，把「导演 → 剧本 → 分镜图 → 视频 → 成片」串成一条链，
> 视频生成全部跑在**你自己电脑上的 ComfyUI + MiniMax-H3**，不依赖任何云端视频服务。

> 做角色一致的片子，先读 [`docs/CHARACTER-CONSISTENCY.md`](docs/CHARACTER-CONSISTENCY.md)
> ——那是踩了一整轮坑后总结的 SOP（ref2va 锁人 + 强制场景描写 + 大动作规则）。

---

## 它是什么

| 能力 | 说明 |
|---|---|
| **无限画布 + 节点** | 导演 / 图片 / 视频 / 文本节点，可连线、可打组复用 |
| **导演节点** | 接「山音超级编剧大师」skill；支持超短片 / 短片 / 长片 / 剧集四种格式，长片剧集走「大纲 → 按集展开」 |
| **视频节点** | 直接调本机 MiniMax-H3：文生视频（T2VA）、首帧生视频（I2VA）、参考图锁角色（Ref2VA） |
| **图片节点** | RealVisXL 出图；单图 / 角色三视图 / 四宫格 / 九宫格；通用「切 N 行 M 列」 |
| **H3 提示词规范** | 按 MiniMax 官方 `h3-prompt-writing` skill 自动组装三段/六段结构，含镜头运动、说话人 ID、台词标签 |
| **一句话成片** | 输入一句话 → 自动分镜 → 逐镜渲染 → 自动拼接（CFR 24fps，带音轨） |
| **LLM 可选** | 不填 API Key 也能用（模板分镜）；填了才真正调用编剧 skill，支持 DeepSeek / OpenAI / Kimi / 智谱 / 通义 / 硅基流动 / OpenRouter / 本地 Ollama |

---

## 前置条件

- **Windows + NVIDIA 显卡**（本机验证环境：RTX 4060 Laptop 8GB / 16GB 内存）
- **ComfyUI**（0.42.x），并且装好：
  - `MiniMax-H3` 相关节点与模型（官方仓库：<https://github.com/MiniMax-AI/MiniMax-H3>）
  - 可选：`ComfyUI-GGUF`、`ComfyUI_IPAdapter_plus`（项目会分别装到自己的 `custom_nodes/`）
- **Python 3.10+**（画布后端只用标准库，不需要装任何依赖）

显存 / 内存参考：8GB 显存能跑 480P 8 步（5 秒镜头约 5 分钟）；16GB 内存是硬下限。

---

## 安装（三步）

```bash
git clone <你的仓库地址> ai-studio
cd ai-studio/studio

# 1) 复制配置，改成你自己机器上的路径
copy config.example.json config.json

# 2) 把 ComfyUI 的模型放进 data 目录（或用自带脚本下载）
python tools/get_model.py SG161222/RealVisXL_V5.0 RealVisXL_V5.0_fp16.safetensors checkpoints

# 3) 启动
start.bat
```

`config.json` 最少要改一项：`comfy_root` —— 指向 ComfyUI 里含 `main.py` 的那层目录。

```json
{
  "data_dir": "D:/AI-Studio",
  "comfy_root": "C:/ComfyUI",
  "port": 8770
}
```

`data_dir` 会在首次启动时自动建好 `models/ output/ input/ temp/`，
并通过生成的 `extra_model_paths.yaml` 挂给 ComfyUI —— **不改动 ComfyUI 原安装**。

打开 <http://127.0.0.1:8770>。

### 不想用内置启动器？

```bat
:: 终端 1：ComfyUI（带兼容补丁，端口 8188）
python tools\start_comfy.py

:: 终端 2：画布后端（端口 8770）
python server.py
```

---

## 目录结构

```
studio/                    代码（很小）
  server.py                后端：静态文件 / 任务队列 / 媒体代理 / 工程存档
  paths.py                 路径解析（环境变量 > config.json > 自动探测）
  h3.py                    ComfyUI 客户端 + H3 计算图构建
  h3_prompt.py             H3 官方提示词规范（T2VA / I2VA / Ref2VA）
  imaging.py               SDXL 出图 / 宫格 / 图生图 / IPAdapter
  screenwriter.py          编剧 skill 调度（大纲 / 展开 / 分镜）
  director.py              轻量分镜（不接 LLM 时的兜底）
  llm.py                   OpenAI 兼容调用层（多服务商降级）
  skills/                  内置 skill（山音编剧 + MiniMax 官方 9 个）
  web/                     画布前端（零依赖、无构建）
  tools/                   启动器、模型下载、拼接、切分
  docs/                    文档（角色一致性 SOP 等）

<data_dir>/                数据（几十 GB，别放 C 盘）
  models/                  所有模型
  output/                  生成的图片、视频、成片
  input/                   首帧图暂存
  temp/                    ComfyUI 临时文件
```

---

## HTTP API（同时也是 Agent 入口）

```bash
# 一条龙：一句话 → 分镜 → 逐镜渲染 → 拼接
POST /api/agent/start   {"idea":"...", "shots":6, "preset":"draft", "use_skill":true, "format":"ultrashort"}
GET  /api/agent/job/<id>

# 只出剧本
POST /api/director/script   {"idea":"...", "format":"ultrashort", "shots":6}

# 长片/剧集：先大纲，再展开某一集
POST /api/director/outline  {"idea":"...", "format":"series", "units":6, "minutes":3}
POST /api/director/expand   {"idea":"...", "unit":{...}, "shots":6}

# 单镜头（可带首帧图 / 参考图锁角色）
POST /api/render  {"prompt":"...", "seconds":5, "preset":"standard", "image":"a.png", "ref_mode":true}

# 按 H3 规范生成提示词
POST /api/prompt/h3  {"action":"...", "duration":5, "shot_size":"中景", "camera":"缓慢推近", "dialogue":"..."}

# skill 列表 / 读文件
GET /api/skills
GET /api/skills/file?name=screenwriting-master&file=SKILL.md
```

> 任何请求都可以带 `"llm": {"api_key":"...", "base_url":"...", "model":"..."}` 临时指定模型；
> 不带就走默认（`config.json` 里的，或纯模板模式）。

---

## 模型清单（按需下载）

| 模型 | 大小 | 用途 | 必需 |
|---|---|---|---|
| MiniMax-H3 fl2va / ref2va / 文本编码器 / VAE / turbo LoRA | ~80GB | 视频生成 | ✅ |
| RealVisXL V5（或任意 SDXL 写实底模） | 6.5GB | 出分镜图 / 角色设定表 | 图片功能需要 |
| ip-adapter-plus_sdxl_vit-h + CLIP-ViT-H | 3.1GB | 参考图引导 | 可选 |
| Qwen-Image-Edit-2509 Q4 | 13GB | 角色一致性（本机跑不动，已弃用） | ❌ |

下载走 HuggingFace 镜像：

```bash
python tools/get_model.py <repo> <filename> <子目录> [--host https://hf-mirror.com]
```

---

## 已知限制

- 单人单卡串行：一次只能跑一个镜头，队列执行
- 动作控制弱：Ref2VA 能锁人和场景，但精细表演做不出来（详见 SOP 文档）
- 口型不对位：台词是模型生成的对白音轨
- 两人对手戏：一张参考图只能锁一个角色
- 8GB 显存 + 16GB 内存是下限，再低会 OOM

---

## 第三方组件与许可

- **MiniMax-H3**：模型与官方 skills 版权归 MiniMax，遵循其仓库许可
- **山音超级编剧大师**：MIT，作者 [@山音](https://github.com/)，本仓库保留了原始 README 与 LICENSE
- **ComfyUI**：GPL-3.0，本项目只是调用它的 HTTP API，不修改其源码
- **RealVisXL**：CreativeML Open RAIL++-M
- 本仓库自身代码：MIT（见 `LICENSE`）

生成内容的版权与合规（尤其涉及知名 IP 的“风格模仿”）由使用者自行负责。
