"""单镜头基准测试：这台机器跑一个镜头到底要多久。

用法：
    python bench.py --preset draft            # 360P / 4 步
    python bench.py --preset standard         # 480P / 8 步
    python bench.py --preset fine --seconds 5 # 720P / 8 步
"""
from __future__ import annotations

import argparse
import json
import sys

import h3


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default=(
        "电影感写实风格，固定机位中景，昏暗的旧书店里，一位穿深色风衣的中年男人"
        "缓缓抬头看向镜头，灰尘在光柱中漂浮，暖色台灯，浅景深。"
        "overall_soundscape: 安静的室内底噪，远处翻书声。"
    ))
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--preset", default="standard", choices=list(h3.PRESETS))
    ap.add_argument("--resolution", default=None)
    ap.add_argument("--aspect", default="9:16")
    ap.add_argument("--steps", type=int, default=None)
    ap.add_argument("--width", type=int, default=480)
    ap.add_argument("--height", type=int, default=864)
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--no-turbo", action="store_true")
    args = ap.parse_args()

    if not h3.alive():
        print("ComfyUI 未启动：先运行 studio/tools/start_comfy.py", file=sys.stderr)
        return 2

    m = h3.models()
    res, steps, lora = h3.resolve_preset(args.preset, m)
    res = args.resolution or res
    steps = args.steps or steps
    print(f"preset={args.preset} resolution={res} steps={steps} lora={lora}", flush=True)

    graph = h3.build_graph(
        args.prompt, resolution=res, aspect=args.aspect,
        width=args.width, height=args.height, seconds=args.seconds,
        steps=steps, seed=args.seed, use_turbo=not args.no_turbo, lora=lora, m=m,
    )
    try:
        pid = h3.submit(graph)
    except RuntimeError as e:
        print("提交失败：\n" + str(e), file=sys.stderr)
        return 3

    print("prompt_id:", pid, flush=True)
    result = h3.wait(pid, on_tick=lambda s: print(f"  ...{s}s", flush=True), poll=3.0)
    print("耗时:", result["elapsed"], "秒")
    print("状态:", result["status"].get("status_str"))
    print("文件:", json.dumps(h3.files_from(result), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
