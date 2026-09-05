"""FlashFrame command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .decode import decode_signal_to_image, decode_video_to_image, mae_images
from .encode import encode_image_to_timeline, prepare_image
from .protocol import (
    DEFAULT_BIT_DEPTH,
    DEFAULT_CODING,
    DEFAULT_FRAME_MS,
    DEFAULT_SIZE,
    CodingName,
)
from .simulate import simulate_timeline


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="flashframe",
        description="FlashFrame — encode images into brightness flashes and decode them back",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("encode", help="Image → flash timeline JSON")
    pe.add_argument("image", type=Path, help="Input image (jpg/png/…)")
    pe.add_argument("-o", "--output", type=Path, required=True, help="Output timeline.json")
    pe.add_argument("--size", type=int, default=DEFAULT_SIZE, help=f"Square size (default {DEFAULT_SIZE})")
    pe.add_argument("--width", type=int, default=None)
    pe.add_argument("--height", type=int, default=None)
    pe.add_argument("--bit-depth", type=int, default=DEFAULT_BIT_DEPTH, choices=[1, 2, 4, 8])
    pe.add_argument("--coding", choices=["manchester", "pwm"], default=DEFAULT_CODING)
    pe.add_argument("--frame-ms", type=float, default=DEFAULT_FRAME_MS)

    ps = sub.add_parser("simulate", help="Timeline → perfect-channel brightness CSV")
    ps.add_argument("timeline", type=Path, help="timeline.json from encode")
    ps.add_argument("-o", "--output", type=Path, required=True, help="Output signal.csv")
    ps.add_argument("--sample-hz", type=float, default=100.0)
    ps.add_argument("--noise", type=float, default=0.0)
    ps.add_argument("--frames-dir", type=Path, default=None, help="Optional PNG frame stack dir")

    pd = sub.add_parser("decode", help="Signal CSV → image (alias: decode-signal)")
    pd.add_argument("signal", type=Path, help="signal.csv")
    pd.add_argument("-o", "--output", type=Path, required=True, help="Output PNG")
    pd.add_argument("--frame-ms", type=float, default=DEFAULT_FRAME_MS)
    pd.add_argument("--coding", choices=["manchester", "pwm"], default=None)
    pd.add_argument("--threshold", type=float, default=None)

    # Explicit alias name from the product brief
    pds = sub.add_parser("decode-signal", help="Signal CSV → image")
    pds.add_argument("signal", type=Path)
    pds.add_argument("-o", "--output", type=Path, required=True)
    pds.add_argument("--frame-ms", type=float, default=DEFAULT_FRAME_MS)
    pds.add_argument("--coding", choices=["manchester", "pwm"], default=None)
    pds.add_argument("--threshold", type=float, default=None)

    pdv = sub.add_parser("decode-video", help="Video → image (mean luminance windows)")
    pdv.add_argument("video", type=Path, help="recording.mp4 / avi / …")
    pdv.add_argument("-o", "--output", type=Path, required=True)
    pdv.add_argument("--frame-ms", type=float, default=DEFAULT_FRAME_MS)
    pdv.add_argument("--coding", choices=["manchester", "pwm"], default=None)

    demo = sub.add_parser("demo", help="Pattern → flashes → picture; write evidence/")
    demo.add_argument("--outdir", type=Path, default=Path("evidence"))
    demo.add_argument("--size", type=int, default=DEFAULT_SIZE)
    demo.add_argument("--bit-depth", type=int, default=DEFAULT_BIT_DEPTH, choices=[1, 2, 4, 8])
    demo.add_argument("--coding", choices=["manchester", "pwm"], default=DEFAULT_CODING)
    demo.add_argument("--frame-ms", type=float, default=DEFAULT_FRAME_MS)

    return p


def cmd_encode(args: argparse.Namespace) -> int:
    meta = encode_image_to_timeline(
        args.image,
        args.output,
        size=args.size,
        width=args.width,
        height=args.height,
        bit_depth=args.bit_depth,
        coding=args.coding,
        frame_ms=args.frame_ms,
    )
    print(json.dumps(meta, indent=2))
    return 0


def cmd_simulate(args: argparse.Namespace) -> int:
    meta = simulate_timeline(
        args.timeline,
        args.output,
        sample_hz=args.sample_hz,
        noise=args.noise,
        frames_dir=args.frames_dir,
    )
    print(json.dumps(meta, indent=2))
    return 0


def cmd_decode(args: argparse.Namespace) -> int:
    meta = decode_signal_to_image(
        args.signal,
        args.output,
        frame_ms=args.frame_ms,
        coding=args.coding,
        threshold=args.threshold,
    )
    print(json.dumps(meta, indent=2))
    return 0 if meta.get("crc_ok") else 1


def cmd_decode_video(args: argparse.Namespace) -> int:
    meta = decode_video_to_image(
        args.video,
        args.output,
        frame_ms=args.frame_ms,
        coding=args.coding,
    )
    print(json.dumps(meta, indent=2))
    return 0 if meta.get("crc_ok") else 1


def _make_demo_pattern(path: Path, size: int) -> None:
    from PIL import Image

    img = Image.new("L", (size, size))
    pixels = []
    for y in range(size):
        for x in range(size):
            # Gradient + checker accent so round-trip is visually obvious
            g = int(255 * x / max(1, size - 1))
            if (x // 4 + y // 4) % 2 == 0:
                g = min(255, g + 40)
            pixels.append(g)
    img.putdata(pixels)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def cmd_demo(args: argparse.Namespace) -> int:
    outdir: Path = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)
    src = outdir / "demo_source.png"
    timeline = outdir / "transmit_timeline.json"
    signal = outdir / "signal.csv"
    dst = outdir / "demo_rebuilt.png"
    report = outdir / "roundtrip.json"
    _make_demo_pattern(src, args.size)
    enc = encode_image_to_timeline(
        src,
        timeline,
        size=args.size,
        bit_depth=args.bit_depth,
        coding=args.coding,
        frame_ms=args.frame_ms,
    )
    resized = outdir / "demo_resized.png"
    img, _ = prepare_image(src, size=args.size)
    img.save(resized)

    # Perfect-channel CSV only (PNG frame stacks are optional via simulate --frames-dir)
    sim = simulate_timeline(
        timeline,
        signal,
        sample_hz=max(50.0, 1000.0 / args.frame_ms * 2.5),
        frames_dir=None,
    )
    dec = decode_signal_to_image(
        signal,
        dst,
        frame_ms=args.frame_ms,
        coding=args.coding,
    )
    err = mae_images(resized, dst)
    result = {
        "encode": enc,
        "simulate": sim,
        "decode": dec,
        "mae": err,
        "pass": bool(dec.get("crc_ok")) and err < 1.0,
    }
    report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["pass"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "encode":
        return cmd_encode(args)
    if args.cmd == "simulate":
        return cmd_simulate(args)
    if args.cmd in ("decode", "decode-signal"):
        return cmd_decode(args)
    if args.cmd == "decode-video":
        return cmd_decode_video(args)
    if args.cmd == "demo":
        return cmd_demo(args)
    parser.error(f"unknown command {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
