"""Perfect-channel simulator: timeline → brightness signal CSV (+ optional PNG stack)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def _load_timeline(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text())
    if data.get("format") != "flashframe-timeline":
        raise ValueError("not a flashframe-timeline JSON")
    return data


def simulate_timeline(
    timeline_path: str | Path,
    signal_path: str | Path,
    *,
    sample_hz: float = 100.0,
    noise: float = 0.0,
    frames_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Render a perfect (or lightly noisy) brightness-over-time signal.

    CSV columns: t_ms,brightness
    Optionally write a PNG frame stack (one black/white image per symbol)
    when frames_dir is set.
    """
    import random

    tl = _load_timeline(timeline_path)
    frame_ms = float(tl["frame_ms"])
    frames = tl["frames"]
    duration_ms = float(tl["duration_ms"])

    # Sample at sample_hz across the whole transmission
    dt_ms = 1000.0 / sample_hz
    rows: list[tuple[float, float]] = []
    t = 0.0
    fi = 0
    while t <= duration_ms + 1e-9:
        # advance frame index
        while fi + 1 < len(frames) and frames[fi + 1]["t_ms"] <= t + 1e-9:
            fi += 1
        level = float(frames[fi]["level"]) if frames else 0.0
        if noise > 0:
            level = max(0.0, min(1.0, level + random.gauss(0, noise)))
        rows.append((round(t, 4), round(level, 6)))
        t += dt_ms

    out = Path(signal_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_ms", "brightness"])
        w.writerows(rows)

    written_frames = 0
    if frames_dir is not None:
        from PIL import Image

        fdir = Path(frames_dir)
        fdir.mkdir(parents=True, exist_ok=True)
        for i, fr in enumerate(frames):
            # 16x16 solid brightness tile
            v = int(round(float(fr["level"]) * 255))
            img = Image.new("L", (16, 16), color=v)
            img.save(fdir / f"frame_{i:05d}.png")
            written_frames += 1

    return {
        "samples": len(rows),
        "sample_hz": sample_hz,
        "duration_ms": duration_ms,
        "frame_ms": frame_ms,
        "signal": str(out),
        "png_frames": written_frames,
        "frames_dir": str(frames_dir) if frames_dir else None,
    }
