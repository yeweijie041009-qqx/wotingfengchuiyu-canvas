# 模型档案（profiles）

一个 `.json` = 一个可用模型。想换模型，加一个文件就行，不用改代码。

## 最快路径

1. 把模型文件放进 `模型目录/<子目录>/`（子目录名和 ComfyUI 一致：`checkpoints` / `diffusion_models` / `loras` / `vae` / `text_encoders` / `clip_vision`）
2. 在 ComfyUI 里搭一个能跑通的工作流，**导出 API 格式**（ComfyUI 设置里勾 `Dev mode` → `Save (API Format)`）
3. 复制 `h3-video.json`，改三处：`id` / `name` / `graph`（粘你导出的 JSON）
4. 在 `params` 里把参数名映射到节点：`"prompt": {"node": "2", "input": "prompt"}`
5. 重启画布，视频节点里就能选到你的模型

## 字段说明

```jsonc
{
  "id": "wan-video",                  // 文件名，唯一
  "name": "Wan 2.6 文生视频",          // 下拉里显示
  "kind": "video",                    // video | image
  "desc": "……",
  "requires": [                       // 缺文件时下拉里显示「缺模型」
    {"dir": "diffusion_models", "file": "wan2.6.safetensors"}
  ],
  "params": {                         // 参数名 → 图里的节点和输入
    "prompt":  {"node": "2", "input": "prompt"},
    "seconds": {"node": "2", "input": "seconds", "type": "float"},
    "seed":    {"node": "7", "input": "seed",   "type": "int"},
    "steps":   {"node": "7", "input": "steps",  "type": "int"},
    "width":   {"node": "4", "input": "width",  "type": "int"},
    "height":  {"node": "4", "input": "height", "type": "int"}
  },
  "image": {                          // 可选：挂了首帧图时怎么接
    "load_node": "12",                // 会在这里插入 LoadImage
    "target_node": "2",               // 把图接到哪个节点
    "target_input": "media_1",
    "set_mode": "i2va"                // 顺便改掉模式参数
  },
  "graph": { … }                      // ComfyUI API 格式的工作流
}
```

## 说明

- 画布**只负责调度**，真正的推理由 ComfyUI 执行。所以"支持哪些模型"= "ComfyUI 支持哪些模型"，这比任何自研引擎都宽。
- 同名参数不写 `type` 时按原值传入，不做类型转换。
- 可选参数（用户没填）不会覆盖模板里的默认值。
- 图片档案（`kind: "image"`）目前用于图片节点，视频节点只列 `kind: "video"` 的档案。
