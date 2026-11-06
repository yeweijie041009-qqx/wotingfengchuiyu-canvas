# 第三方组件声明

本仓库包含或引用以下第三方内容，版权归各自作者所有。分发时请保留本文件与原始许可。

## 山音超级编剧大师（`skills/screenwriting-master/`）

- 作者：@山音
- 许可：MIT（见 `skills/LICENSE`）
- 来源：本项目作者提供的 skill 包
- 使用要求：保留原作者署名，禁止二次售卖 skill 文件本身

## MiniMax-H3 官方 Skills（`skills/minimax-h3/`）

- 来源：<https://github.com/MiniMax-AI/MiniMax-H3/tree/main/skills>
- 版权归 MiniMax 所有，遵循其仓库许可
- 本项目仅作提示词规范参考与本地调度使用，未修改原文
- 若上游许可不允许再分发，请删除该目录并从上游自行拉取：

  ```bash
  git clone --depth 1 https://github.com/MiniMax-AI/MiniMax-H3
  cp -r MiniMax-H3/skills/* studio/skills/minimax-h3/
  ```

## MiniMax-H3 模型权重

- 不在本仓库内分发，需用户自行从官方渠道下载
- 使用前请阅读官方模型许可

## ComfyUI

- 许可：GPL-3.0
- 本项目仅通过 HTTP API 调用，不修改其源码，不静态链接

## RealVisXL V5

- 许可：CreativeML Open RAIL++-M
- 不在本仓库内分发

## SDXL base 1.0

- 许可：CreativeML Open RAIL++-M
- 不在本仓库内分发

## IP-Adapter

- 来源：<https://huggingface.co/h94/IP-Adapter>
- 不在本仓库内分发

---

生成内容的版权与合规（尤其是对知名 IP 的“风格模仿”）由使用者自行负责。
