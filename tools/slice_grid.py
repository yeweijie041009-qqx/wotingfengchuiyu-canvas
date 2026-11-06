"""把一张宫格图切成独立分镜（跑在 ComfyUI 的 venv 里，需要 Pillow）。

用法：python slice_grid.py <源文件> <输出目录> <rows> <cols> [前缀]
输出：每个格子一个 png，打印 JSON 列表。
"""
from __future__ import annotations

import json
import os
import sys

from PIL import Image


def main() -> int:
    if len(sys.argv) < 5:
        print(__doc__, file=sys.stderr)
        return 2
    src, outdir, rows, cols = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    prefix = sys.argv[5] if len(sys.argv) > 5 else "slice"
    os.makedirs(outdir, exist_ok=True)

    im = Image.open(src)
    w, h = im.size
    cw, ch = w // cols, h // rows
    out = []
    for r in range(rows):
        for c in range(cols):
            box = (c * cw, r * ch, (c + 1) * cw, (r + 1) * ch)
            name = f"{prefix}_{r + 1}{c + 1}.png"
            path = os.path.join(outdir, name)
            im.crop(box).save(path)
            out.append({"filename": name, "width": cw, "height": ch,
                        "row": r + 1, "col": c + 1})
    print(json.dumps({"count": len(out), "files": out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
