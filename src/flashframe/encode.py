"""Encode images into FlashFrame flash timelines."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image

from .protocol import (
    DEFAULT_BIT_DEPTH,
    DEFAULT_CODING,
    DEFAULT_FRAME_MS,
    DEFAULT_SIZE,
    HEADER_BYTES,
    LEVEL_BRIGHT,
    LEVEL_DARK,
    PREAMBLE_BITS,
    CodingName,
    bytes_to_bits,
    checksum32,
    encode_bits,
    pack_header,
    pixels_to_bits,
)


def prepare_image(
    path: str | Path,
    size: int = DEFAULT_SIZE,
    width: int | None = None,
    height: int | None = None,
) -> tuple[Image.Image, bytes]:
    """Load, resize to grayscale, return (image, pixel bytes 0..255)."""
    img = Image.open(path)
    w = width or size
    h = height or size
    gray = img.convert("L").resize((w, h), Image.Resampling.LANCZOS)
    return gray, gray.tobytes()


def _symbol_level(bit: int) -> float:
    return LEVEL_BRIGHT if bit else LEVEL_DARK


def build_timeline_frames(
    symbols: list[int],
    frame_ms: float,
    t0: float = 0.0,
) -> list[dict[str, Any]]:
    """Build [{t_ms, duration_ms, level}, ...] from brightness symbols."""
    frames: list[dict[str, Any]] = []
    t = t0
    for s in symbols:
        frames.append(
            {
                "t_ms": round(t, 3),
                "duration_ms": frame_ms,
                "level": _symbol_level(s),
            }
        )
        t += frame_ms
    return frames


def encode_image_to_timeline(
    image_path: str | Path,
    timeline_path: str | Path,
    *,
    size: int = DEFAULT_SIZE,
    width: int | None = None,
    height: int | None = None,
    bit_depth: int = DEFAULT_BIT_DEPTH,
    coding: CodingName = DEFAULT_CODING,
    frame_ms: float = DEFAULT_FRAME_MS,
) -> dict[str, Any]:
    """Encode an image to a flash timeline JSON. Returns metadata."""
    img, pixels = prepare_image(image_path, size=size, width=width, height=height)
    w, h = img.size
    crc = checksum32(pixels)
    header = pack_header(w, h, bit_depth, coding, crc)

    # Stream: preamble (raw) + coded(header_bits + payload_bits)
    payload_bits = pixels_to_bits(pixels, bit_depth)
    data_bits = bytes_to_bits(header) + payload_bits
    coded = encode_bits(data_bits, coding)

    all_symbols = list(PREAMBLE_BITS) + coded
    frames = build_timeline_frames(all_symbols, frame_ms)

    timeline = {
        "format": "flashframe-timeline",
        "version": 1,
        "frame_ms": frame_ms,
        "coding": coding,
        "bit_depth": bit_depth,
        "width": w,
        "height": h,
        "crc32": f"{crc:08x}",
        "preamble_symbols": len(PREAMBLE_BITS),
        "coded_symbols": len(coded),
        "total_symbols": len(all_symbols),
        "duration_ms": round(len(all_symbols) * frame_ms, 3),
        "header_bytes": HEADER_BYTES,
        "frames": frames,
    }

    out = Path(timeline_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(timeline, indent=2) + "\n")

    return {
        "width": w,
        "height": h,
        "bit_depth": bit_depth,
        "coding": coding,
        "crc32": f"{crc:08x}",
        "frame_ms": frame_ms,
        "symbols": len(all_symbols),
        "duration_ms": timeline["duration_ms"],
        "timeline": str(out),
        "pixels": len(pixels),
    }
