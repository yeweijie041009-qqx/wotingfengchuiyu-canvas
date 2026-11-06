"""把多张分镜图拼成一张宫格联络表（PIL，跑在 ComfyUI 的 venv 里）。

用法：python tile_grid.py out.png rows cols in1.png in2.png ...
"""
from __future__ import annotations

import sys

from PIL import Image

GUTTER = 8
BG = (250, 250, 250)


def main() -> int:
    if len(sys.argv) < 5:
        print(__doc__, file=sys.stderr)
        return 2
    out_path, rows, cols = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    inputs = sys.argv[4:]
    if len(inputs) < rows * cols:
        print(f"need {rows * cols} images, got {len(inputs)}", file=sys.stderr)
        return 3

    first = Image.open(inputs[0])
    pw, ph = first.size
    W = pw * cols + GUTTER * (cols + 1)
    H = ph * rows + GUTTER * (rows + 1)
    canvas = Image.new("RGB", (W, H), BG)

    for i, path in enumerate(inputs[: rows * cols]):
        r, c = divmod(i, cols)
        im = Image.open(path).convert("RGB")
        if im.size != (pw, ph):
            im = im.resize((pw, ph), Image.LANCZOS)
        canvas.paste(im, (GUTTER + c * (pw + GUTTER), GUTTER + r * (ph + GUTTER)))

    canvas.save(out_path)
    print(f"ok {out_path} {W}x{H}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
