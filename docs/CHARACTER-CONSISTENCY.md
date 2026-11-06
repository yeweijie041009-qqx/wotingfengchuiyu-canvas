# 角色一致性 SOP（本地 H3 实测版）

> 结论先说：本机唯一可靠的“锁人”方式是 **MiniMax-H3 的 ref2va（参考生视频）**。
> IPAdapter / i2i / 图生图 都做不到身份级锁定，别再在这上面浪费时间。

---

## 0. 一张表看懂

| 手段 | 锁人物 | 锁场景 | 锁动作 | 适用 |
|---|---|---|---|---|
| **ref2va + 参考图 + 强制场景句** | ✅ 强 | ✅ 强 | ⚠️ 弱 | **所有剧情镜头（推荐）** |
| i2va（首帧生视频） | 取决于首帧 | ✅ 强 | ✅ 强 | 有精确关键帧时 |
| t2va（纯文生） | ❌ 每镜都变 | ✅ | ✅ | 空镜、环境镜头 |
| SDXL + IPAdapter（图片端） | ⚠️ 同类人 | — | — | 出设定图，不是出分镜 |
| i2i（图生图 denoise 0.45） | ✅ 锁住 | ❌ 场景也锁死 | ❌ | 只换画风，不换场景 |

---

## 1. 标准流程（四步）

### ① 出「角色设定表」

画布 → `+ 图片` → 模式选 **角色三视图** → 提示词写清楚外观：

```
a 50-year-old bald man with a big brown mustache, white short-sleeve polo shirt
with brown stains, dark blue trousers, brown boots, full body turnaround,
front / side / back view, plain white background, 2D cartoon, thick black outlines
```

约 24–30 秒。得到一个多视图设定表。

### ② 裁出「正面全身」单图

画布 → 图片节点 → **「切成 1 行 N 列」→ 切分**

> ⚠️ **不要把整张多视图直接当参考图**。模型会混淆该学哪个角度，结果人不像人。
> 只取最左边的正面视图。

### ③ 每镜用 ref2va

视频节点 → 首帧选这张正面图 → 模式选 **「参考图锁角色」**。

---

## 2. 提示词模板（直接抄）

ref2va 走官方六段结构，系统会自动组装。你只需要填两个字段：

**subject（角色描述，越具体越稳）**

```
bald middle-aged man with a big brown mustache, plain white short-sleeve polo shirt
with brown stains, dark blue trousers, brown boots, 2D cartoon, thick black outlines, flat colors
```

**action（场景 + 大动作）——按这个固定句式写**

```
The scene is a small home kitchen with white cabinets, a window and a counter.
He walks in from the doorway carrying a silver toaster with both hands and stops at the counter.
The background must stay inside the kitchen.
```

三句话结构：
1. `The scene is ...` — **先把环境写死**
2. 主体 + **一个大动作**（走 / 放下 / 转身 / 举起 / 回头 / 站住）
3. `The background must stay inside ...` — **末尾再强调一次**

**这条“重复强调背景”是本机实测出来的关键技巧**，不写就会跑进树林。

---

## 3. 动作写作规则（血泪教训）

| 写法 | 结果 |
|---|---|
| `subtle camera move, natural motion` | ❌ 出静帧 |
| `他后仰，双手举起，眼睛瞪大` | ⚠️ 大概率做不出来，退化成站着 |
| `He walks in carrying a toaster and stops at the counter` | ✅ 能做出来 |
| `He sets it down and plugs the cable into the wall socket` | ✅ 能做出来 |
| `He jerks backward with both hands raised` | ⚠️ 时好时坏 |

**结论：只写「走、站、放下、拿起、转身、回头、举起」这类位移型大动作。
不要写「表情变化、精细手势、连续两个以上动作」。**

---

## 4. 已知限制（别指望）

- **动作幅度**：精细表演做不出来
- **口型对位**：台词是模型生成的对白音轨，嘴型不对
- **两人对手戏**：ref2va 一张参考图只能锁一个人
- **长镜头调度**：单条 4–15 秒，超过就要拼
- **风格迁移**：画风由参考图决定；想要别的画风得换参考图

---

## 5. 参数速查

| 档位 | 分辨率 | 耗时（5 秒镜头） | 用途 |
|---|---|---|---|
| 草稿 | 360P / 4 步 | ~95 秒 | 抽卡试错 |
| 标准 | 480P / 8 步 | ~324 秒 | 定稿 |
| 720P / 8 步 | — | 未测（显存吃紧） | — |

一条 6 镜短剧（草稿）≈ 10 分钟；标准档 ≈ 35 分钟。

---

## 6. 走不通的路（省得再试）

| 尝试 | 结果 |
|---|---|
| IPAdapter 0.45 | 同类人，不同脸 |
| IPAdapter 0.7 | 把参考图的场景整个拖回来 |
| IPAdapter plus-face 0.75 | 换了个人种 |
| i2i denoise 0.45/0.5 | 脸保住了，场景也锁死了 |
| SDXL base + 卡通提示词 | 风格对了，人崩了（眼镜/围裙乱入） |
| SDXL base + IPAdapter 0.8 | 脸严重变形 |
| Qwen-Image-Edit 13GB | 16GB 内存跑不动，35 分钟未出图，已删 |

---

## 7. 如果以后要“真正锁脸”

按代价从低到高：

1. **InstantID + insightface**：PyPI 只有源码包，需要编译（VS Build Tools），Windows + Python 3.13 上失败率高
2. **Qwen-Image-Edit-2509**：需要 ≥32GB 内存 + 24GB 显存才实用
3. **换云端 API**（可灵 / 即梦）：一致性、速度、画质都解决，但不再是纯本地

---

## 8. 排查清单

| 现象 | 原因 | 处理 |
|---|---|---|
| 人物每镜都不一样 | 用了 t2va 或没挂参考图 | 改 ref2va + 挂正面图 |
| 场景跑到户外 | 没写场景句 | 开头写 `The scene is...`，结尾再强调 |
| 画面像静帧 | 提示词写了 `subtle / natural motion` | 换成明确动词 |
| 人物变形/多手多脚 | 参考图是多视图拼版 | 裁成单张正面 |
| 台词没声音 | 台词没包在 `<d>` 里 | 检查提示词格式 |
