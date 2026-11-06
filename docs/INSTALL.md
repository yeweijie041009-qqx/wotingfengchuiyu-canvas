# 安装说明书（给朋友的版本）

> 目标：从一台干净的 Windows 电脑，到能打开画布、生成第一条视频。
> 全程大约 **1–2 小时**，其中 80% 时间在下载模型（约 80GB）。
> 每一步都有「怎么算成功」，卡住了看最后的 **常见问题**。

---

## 0. 先确认你的电脑够不够

| 项 | 最低 | 建议 |
|---|---|---|
| 显卡 | NVIDIA，**8GB 显存** | 12GB 以上 |
| 内存 | **16GB** | 32GB |
| 硬盘 | **150GB 空闲**（模型 80GB + 缓存） | SSD，放在非 C 盘 |
| 系统 | Windows 10/11 | — |
| 网络 | 能访问 GitHub / HuggingFace 镜像 | 有代理更顺 |

> ⚠️ AMD 显卡、Mac、纯核显：**跑不了**，这套只支持 NVIDIA + CUDA。

---

## 1. 装 ComfyUI（约 20 分钟）

ComfyUI 是"引擎"，画布只是遥控器。

1. 打开 <https://www.comfy.org/download>
2. 下载 **Windows 版**（Desktop 安装包，一键装，自带 Python 和 CUDA 环境）
3. 安装到**非 C 盘**，例如 `E:\Comfy-Desktop`
4. 装完先启动一次，看到浏览器打开一个节点界面，就算成功

✅ **怎么算成功**：ComfyUI 能打开，界面能拖动。

记下它的安装位置，第 4 步要用，例如：
`E:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI`

> 里面必须有一个 `main.py` 文件，这是判断路径对不对的标准。

---

## 2. 装 MiniMax-H3 的模型和节点（最耗时）

### 2.1 下载模型

模型官方地址（二选一，国内建议用 ModelScope）：

- HuggingFace：<https://huggingface.co/MiniMaxAI/MiniMax-H3>
- ModelScope：<https://modelscope.cn/organization/minimax>

放进 ComfyUI 的 `models` 目录，对应关系：

| 文件类型 | 放到 |
|---|---|
| 主模型（`*_convrot.safetensors`，fl2va / ref2va） | `models\diffusion_models\` |
| 文本编码器（`qwen3vl_32b_*`） | `models\text_encoders\` |
| 视频 VAE（`minimax_h3_video_vae_*`） | `models\vae\` |
| 音频 VAE（`minimax_h3_audio_vae_*`） | `models\vae\` |
| 加速 LoRA（`*turbo*`） | `models\loras\` |

参考体积（我们本机在用的量化版）：

```
minimax_h3_fl2va_pruned_int8_convrot.safetensors     19.5 GB
minimax_h3_ref2va_int8_convrot.safetensors           31.7 GB
qwen3vl_32b_minimax_h3_int8_convrot.safetensors      25.3 GB
minimax_h3_video_vae_fp16.safetensors                 4.9 GB
minimax_h3_audio_vae_fp32.safetensors                 0.6 GB
minimax_h3_fl2v_lightx2v_turbo_4step_*.safetensors    0.3 GB
minimax_h3_fl2v_turbo_8step_*.safetensors             1.8 GB
```

> 找不到同名的 int8 量化版，就用官方原始权重，也能跑，只是更吃显存、更慢。

### 2.2 装 H3 的 ComfyUI 节点

在 ComfyUI 的 `custom_nodes` 目录里，用 Git 拉这三个（没有 Git 就下 ZIP 解压进去）：

```bat
cd /d E:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\custom_nodes
git clone https://github.com/nkxx188/ComfyUI-MiniMaxH3-Easy.git
git clone https://github.com/jlucasmcrell/ComfyUI-H3-Multishot.git
git clone https://github.com/yichengup/ComfyUI-YCNodes-MiniMax-H3.git
```

> 这几个是社区做的 H3 节点包，负责把模型串成能用的计算图。
> 装完重启 ComfyUI，节点面板里能看到 **MiniMax H3 Easy** 分类就对了。

✅ **怎么算成功**：ComfyUI 里搜 "MiniMaxH3EasyLoader" 能搜到这个节点。

---

## 3. 下载本项目（约 1 分钟）

```bat
cd /d D:\
git clone https://github.com/yeweijie041009-qqx/wotingfengchuiyu-canvas.git
```

没有 Git？在仓库页面点 **Code → Download ZIP**，解压到 `D:\wotingfengchuiyu-canvas`。

✅ **怎么算成功**：`D:\wotingfengchuiyu-canvas\studio\server.py` 这个文件存在。

---

## 4. 配置（约 5 分钟）

1. 进到 `studio` 目录
2. 把 `config.example.json` **复制一份**，改名成 `config.json`
3. 用记事本打开，改这两个值：

```json
{
  "data_dir": "D:/AI-Studio",
  "comfy_root": "E:/Comfy-Desktop/ComfyUI-Installs/ComfyUI/ComfyUI",
  "port": 8770
}
```

| 字段 | 填什么 |
|---|---|
| `data_dir` | 模型和成品放哪。**别放 C 盘**，建议 `D:/AI-Studio` |
| `comfy_root` | 第 1 步里含 `main.py` 的那层目录（斜杠用 `/` 或 `\\`） |

保存。

### 把模型挪到 data 目录（可选，但推荐）

`data_dir` 下的 `models\` 会被自动挂给 ComfyUI，等于多一个模型仓库。
可以把第 2 步下载的模型直接放到 `D:\AI-Studio\models\` 对应子目录，
这样 ComfyUI 原目录不占地方，重装 ComfyUI 也不丢模型。

✅ **怎么算成功**：`config.json` 里 `comfy_root` 指向的目录下真的有 `main.py`。

---

## 5. 启动

双击 `studio\start.bat`。

它做三件事：起 ComfyUI（8188）→ 起画布后端（8770）→ 打开浏览器。

✅ **怎么算成功**：浏览器打开 <http://127.0.0.1:8770>，右上角显示 **ComfyUI 在线**（绿点）。

第一次启动会加载 80GB 权重，**要等 1–3 分钟**，期间画布可能显示"未启动"，刷新即可。

---

## 6. 生成第一条视频

1. 顶部输入框写一句话，例如：`雨夜，外卖员敲开一扇门，开门的是十年后的自己`
2. 镜头数选 `2`，质量档选 **草稿 360P/4步**（快，一个镜头约 1.5 分钟）
3. 点「一句话成片」
4. 等 3–5 分钟，画布上会自动出现节点和成片

✅ **怎么算成功**：视频节点里能播放，并且有声音。

---

## 7. 可选增强

| 想做的事 | 需要额外装 |
|---|---|
| 出图片 / 角色三视图 / 分镜宫格 | 一个 SDXL 写实底模（约 6.5GB）→ `models\checkpoints\` |
| 参考图引导（IPAdapter） | `ComfyUI_IPAdapter_plus` 节点 + 两个权重 |
| 让导演真正写剧本（而不是套模板） | 一个 LLM API Key，画布右上角 🔑 里填 |
| 加载 GGUF 量化模型 | `ComfyUI-GGUF` 节点 + `gguf` 包 |

模型可以用项目自带脚本下（走国内镜像）：

```bat
cd /d D:\wotingfengchuiyu-canvas\studio
python tools\get_model.py SG161222/RealVisXL_V5.0 RealVisXL_V5.0_fp16.safetensors checkpoints
```

---

## 常见问题

**Q1：双击 start.bat 一闪就没了**
说明 Python 没装或不在 PATH。装 <https://www.python.org/downloads/>，安装时勾 **Add Python to PATH**。

**Q2：提示"找不到 ComfyUI"**
`config.json` 里的 `comfy_root` 不对。判断标准：那个目录下要有 `main.py`。
注意 Windows 路径要写成 `E:/xxx/xxx` 或 `E:\\xxx\\xxx`，不能直接粘贴带单反斜杠的。

**Q3：画布一直显示"ComfyUI 未启动"**
- ComfyUI 还没加载完（等 1–3 分钟）
- 或者 8188 端口被占用：先关掉 ComfyUI Desktop 自己的窗口，只用 `start.bat` 启动
- 检查：浏览器打开 <http://127.0.0.1:8188> 能不能看到节点界面

**Q4：点生成报 OOM / out of memory**
显存不够。把质量档降到 **草稿 360P**，镜头时长改短（3 秒），别同时开浏览器视频。

**Q5：视频出来了但人物每镜都不一样**
正常。H3 参考生视频要挂参考图才锁人 —— 见 `docs/CHARACTER-CONSISTENCY.md`。

**Q6：下载模型太慢**
用 ModelScope，或用国内镜像：

```bat
python tools\get_model.py <仓库名> <文件名> <子目录> --host https://hf-mirror.com
```

**Q7：能不能不装模型，直接调云端？**
可以，但那是另一套东西。本项目定位是**全本地**，不依赖云端视频服务。

---

## 目录速查

```
D:\wotingfengchuiyu-canvas\studio   代码（几十 MB）
D:\AI-Studio\models                 模型（80GB+）
D:\AI-Studio\output                 生成的视频、图片
D:\wotingfengchuiyu-canvas\studio\config.json   你的配置（不要分享给别人）
```

---

## 还是装不上？

把你的情况发我，附上：
1. `config.json` 内容（**别带 api_key**）
2. 报错截图
3. 显卡型号 + 内存大小

大部分问题都出在 `comfy_root` 路径和模型放置目录上。
