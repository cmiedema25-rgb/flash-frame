"""Decode FlashFrame brightness signals / video back into images."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .protocol import (
    DEFAULT_CODING,
    DEFAULT_FRAME_MS,
    HEADER_BYTES,
    PREAMBLE_BITS,
    CodingName,
    bits_to_bytes,
    bits_to_pixels,
    checksum32,
    decode_bits,
    unpack_header,
)


def load_signal_csv(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Load t_ms,brightness CSV → (times_ms, brightness)."""
    times: list[float] = []
    vals: list[float] = []
    with Path(path).open(newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "brightness" not in reader.fieldnames:
            # fallback: two numeric columns
            f.seek(0)
            reader2 = csv.reader(f)
            for row in reader2:
                if not row or row[0].lower().startswith("t"):
                    continue
                times.append(float(row[0]))
                vals.append(float(row[1]))
        else:
            for row in reader:
                times.append(float(row["t_ms"]))
                vals.append(float(row["brightness"]))
    return np.asarray(times, dtype=np.float64), np.asarray(vals, dtype=np.float64)


def _binarize(brightness: np.ndarray, threshold: float | None = None) -> np.ndarray:
    if threshold is None:
        threshold = float(np.median(brightness))
        # if nearly constant, use midpoint of range
        lo, hi = float(brightness.min()), float(brightness.max())
        if hi - lo < 1e-6:
            threshold = 0.5
        else:
            threshold = (lo + hi) / 2.0
    return (brightness >= threshold).astype(np.int32)


def _resample_to_symbols(
    times_ms: np.ndarray,
    bits: np.ndarray,
    frame_ms: float,
    n_symbols: int | None = None,
    t0: float | None = None,
) -> np.ndarray:
    """Sample one bit per frame_ms window starting at t0 (or times[0])."""
    if t0 is None:
        t0 = float(times_ms[0])
    if n_symbols is None:
        duration = float(times_ms[-1] - t0)
        n_symbols = max(1, int(round(duration / frame_ms)))
    symbols = np.zeros(n_symbols, dtype=np.int32)
    for i in range(n_symbols):
        center = t0 + (i + 0.5) * frame_ms
        # nearest sample
        j = int(np.argmin(np.abs(times_ms - center)))
        symbols[i] = bits[j]
    return symbols


def find_preamble(
    symbols: np.ndarray,
    preamble: tuple[int, ...] = PREAMBLE_BITS,
) -> int:
    """Return start index of preamble in symbol stream, or -1."""
    pref = np.asarray(preamble, dtype=np.int32)
    n = len(pref)
    best_i = -1
    best_score = -1
    for i in range(0, max(0, len(symbols) - n + 1)):
        score = int(np.sum(symbols[i : i + n] == pref))
        if score > best_score:
            best_score = score
            best_i = i
    # require mostly correct match
    if best_score < n - 1:
        return -1
    return best_i


def decode_symbols_to_image(
    symbols: np.ndarray,
    *,
    coding: CodingName | None = None,
    image_path: str | Path | None = None,
    expect_crc: bool = True,
) -> dict[str, Any]:
    """Decode a full symbol stream (preamble + coded data) to an image."""
    start = find_preamble(symbols)
    if start < 0:
        raise ValueError("preamble not found in brightness stream")
    data_syms = symbols[start + len(PREAMBLE_BITS) :]

    # Peek header with default coding if not specified; try manchester first
    candidates: list[CodingName] = (
        [coding] if coding is not None else ["manchester", "pwm"]
    )
    last_err: Exception | None = None
    for cand in candidates:
        try:
            return _decode_with_coding(
                data_syms, cand, image_path=image_path, expect_crc=expect_crc
            )
        except Exception as e:  # noqa: BLE001 — try next coding
            last_err = e
            continue
    raise ValueError(f"failed to decode with candidates {candidates}: {last_err}")


def _decode_with_coding(
    data_syms: np.ndarray,
    coding: CodingName,
    *,
    image_path: str | Path | None,
    expect_crc: bool,
) -> dict[str, Any]:
    bits = decode_bits(data_syms.tolist(), coding)
    header = bits_to_bytes(bits, HEADER_BYTES)
    width, height, bit_depth, coding_h, crc = unpack_header(header)
    # Prefer coding from header
    if coding_h != coding:
        bits = decode_bits(data_syms.tolist(), coding_h)
        header = bits_to_bytes(bits, HEADER_BYTES)
        width, height, bit_depth, coding_h, crc = unpack_header(header)
        coding = coding_h

    n_pixels = width * height
    need_bits = HEADER_BYTES * 8 + n_pixels * bit_depth
    if len(bits) < need_bits:
        raise ValueError(f"incomplete bitstream: got {len(bits)} need {need_bits}")

    payload_bits = bits[HEADER_BYTES * 8 : need_bits]
    pixels = bits_to_pixels(payload_bits, n_pixels, bit_depth)
    got_crc = checksum32(pixels)
    crc_ok = got_crc == crc
    if expect_crc and not crc_ok:
        pass  # still emit image; flag in meta

    meta: dict[str, Any] = {
        "width": width,
        "height": height,
        "bit_depth": bit_depth,
        "coding": coding,
        "crc32_expected": f"{crc:08x}",
        "crc32_got": f"{got_crc:08x}",
        "crc_ok": crc_ok,
        "pixels": n_pixels,
    }

    if image_path is not None:
        out = Path(image_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        img = Image.frombytes("L", (width, height), pixels)
        img.save(out)
        meta["image"] = str(out)

    return meta


def decode_signal_to_image(
    signal_path: str | Path,
    image_path: str | Path,
    *,
    frame_ms: float = DEFAULT_FRAME_MS,
    coding: CodingName | None = None,
    threshold: float | None = None,
) -> dict[str, Any]:
    """Decode a brightness CSV signal to a PNG."""
    times, brightness = load_signal_csv(signal_path)
    bits = _binarize(brightness, threshold=threshold)
    # Over-estimate symbols; preamble finder will locate start
    duration = float(times[-1] - times[0]) if len(times) > 1 else frame_ms
    n_sym = max(1, int(round(duration / frame_ms)) + 4)
    symbols = _resample_to_symbols(times, bits, frame_ms, n_symbols=n_sym, t0=float(times[0]))
    meta = decode_symbols_to_image(
        symbols, coding=coding, image_path=image_path, expect_crc=True
    )
    meta["signal"] = str(signal_path)
    meta["frame_ms"] = frame_ms
    return meta


def decode_video_to_image(
    video_path: str | Path,
    image_path: str | Path,
    *,
    frame_ms: float = DEFAULT_FRAME_MS,
    coding: CodingName | None = None,
    roi: tuple[int, int, int, int] | None = None,
) -> dict[str, Any]:
    """Decode by sampling mean luminance per time window from a video file.

    Prefers OpenCV if installed; otherwise raises with install hint.
    """
    try:
        import cv2  # type: ignore
    except ImportError as e:
        raise ImportError(
            "decode-video requires opencv-python-headless. "
            "Install with: pip install 'flash-frame[webcam]' "
            "or decode a CSV via `flashframe decode signal.csv`."
        ) from e

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    times: list[float] = []
    vals: list[float] = []
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if roi is not None:
            x, y, w, h = roi
            frame = frame[y : y + h, x : x + w]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean = float(np.mean(gray)) / 255.0
        times.append(idx * 1000.0 / fps)
        vals.append(mean)
        idx += 1
    cap.release()

    if not times:
        raise ValueError("empty video / no frames")

    # Write temp-like in-memory path through arrays
    t_arr = np.asarray(times, dtype=np.float64)
    b_arr = np.asarray(vals, dtype=np.float64)
    bits = _binarize(b_arr)
    duration = float(t_arr[-1] - t_arr[0])
    n_sym = max(1, int(round(duration / frame_ms)) + 4)
    symbols = _resample_to_symbols(t_arr, bits, frame_ms, n_symbols=n_sym, t0=float(t_arr[0]))
    meta = decode_symbols_to_image(
        symbols, coding=coding, image_path=image_path, expect_crc=True
    )
    meta["video"] = str(video_path)
    meta["video_fps"] = fps
    meta["video_frames"] = idx
    meta["frame_ms"] = frame_ms
    return meta


def mae_images(a_path: str | Path, b_path: str | Path) -> float:
    """Mean absolute error between two same-size images (0..255 scale)."""
    a = np.array(Image.open(a_path).convert("L"), dtype=np.float64)
    b = np.array(Image.open(b_path).convert("L"), dtype=np.float64)
    if a.shape != b.shape:
        b_img = Image.open(b_path).convert("L").resize((a.shape[1], a.shape[0]))
        b = np.array(b_img, dtype=np.float64)
    return float(np.mean(np.abs(a - b)))
