"""把多个 mp4 拼成一个恒定帧率的成片（PyAV，重编码，跑在 ComfyUI 的 venv 里）。

用法：python concat.py out.mp4 in1.mp4 in2.mp4 ...

为什么重编码而不是直接 remux：H3 输出的时间戳带编码器起始偏移，直接搬会导致
播放器时间戳乱序，画面一卡一卡的。这里按固定 24fps 重新编码，保证严格 CFR。
"""
from __future__ import annotations

import sys
from fractions import Fraction

import av

FPS = 24
AUDIO_RATE = 48000


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: concat.py out.mp4 in1.mp4 in2.mp4 ...", file=sys.stderr)
        return 2
    out_path, inputs = sys.argv[1], sys.argv[2:]

    with av.open(inputs[0]) as probe:
        vs = probe.streams.video[0]
        width, height = vs.width, vs.height

    out = av.open(out_path, "w", format="mp4", options={"movflags": "faststart"})
    ov = out.add_stream("libx264", rate=FPS)
    ov.width, ov.height = width, height
    ov.pix_fmt = "yuv420p"
    ov.time_base = Fraction(1, FPS)
    ov.options = {"crf": "18", "preset": "veryfast"}

    oa = out.add_stream("aac", rate=AUDIO_RATE)
    oa.layout = "stereo"
    oa.time_base = Fraction(1, AUDIO_RATE)
    resampler = av.AudioResampler(format="fltp", layout="stereo", rate=AUDIO_RATE)

    idx = 0
    for path in inputs:
        with av.open(path) as src:
            # 必须一次性解复用视频+音频：容器是单向的，先解完视频就取不到音频了
            wanted = [src.streams.video[0]]
            if src.streams.audio:
                wanted.append(src.streams.audio[0])
            for frame in src.decode(*wanted):
                if isinstance(frame, av.AudioFrame):
                    for rf in resampler.resample(frame):
                        rf.pts = None
                        for pkt in oa.encode(rf):
                            out.mux(pkt)
                    continue
                if (frame.width, frame.height) != (width, height):
                    frame = frame.reformat(width=width, height=height, format="yuv420p")
                frame.pts = idx
                frame.time_base = Fraction(1, FPS)
                for pkt in ov.encode(frame):
                    out.mux(pkt)
                idx += 1

    for pkt in ov.encode(None):
        out.mux(pkt)
    try:
        for rf in resampler.resample(None):
            rf.pts = None
            for pkt in oa.encode(rf):
                out.mux(pkt)
    except Exception:
        pass
    for pkt in oa.encode(None):
        out.mux(pkt)
    out.close()

    print(f"ok {out_path} frames={idx} fps={FPS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
