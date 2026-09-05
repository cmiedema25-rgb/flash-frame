"""Round-trip tests: image → timeline → signal → image."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from flashframe.decode import decode_signal_to_image, mae_images
from flashframe.encode import encode_image_to_timeline, prepare_image
from flashframe.protocol import (
    PREAMBLE_BITS,
    bits_to_bytes,
    bits_to_pixels,
    bytes_to_bits,
    checksum32,
    decode_bits,
    encode_bits,
    manchester_decode,
    manchester_encode,
    pack_header,
    pixels_to_bits,
    unpack_header,
)
from flashframe.simulate import simulate_timeline


def _gradient(path: Path, size: int = 16) -> None:
    img = Image.new("L", (size, size))
    pix = [int(255 * x / max(1, size - 1)) for y in range(size) for x in range(size)]
    img.putdata(pix)
    img.save(path)


def test_manchester_roundtrip():
    bits = [0, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0, 0]
    sym = manchester_encode(bits)
    assert len(sym) == len(bits) * 2
    assert manchester_decode(sym) == bits


def test_header_roundtrip():
    crc = checksum32(b"abc")
    h = pack_header(32, 24, 8, "manchester", crc)
    assert len(h) == 11
    w, ht, bd, coding, c = unpack_header(h)
    assert (w, ht, bd, coding, c) == (32, 24, 8, "manchester", crc)


def test_pixel_bits_roundtrip():
    pixels = bytes(range(16))
    bits = pixels_to_bits(pixels, 8)
    back = bits_to_pixels(bits, 16, 8)
    assert back == pixels


@pytest.mark.parametrize("coding", ["manchester", "pwm"])
@pytest.mark.parametrize("size", [8, 16])
def test_full_roundtrip(tmp_path: Path, coding: str, size: int):
    src = tmp_path / "src.png"
    timeline = tmp_path / "timeline.json"
    signal = tmp_path / "signal.csv"
    out = tmp_path / "out.png"
    resized = tmp_path / "resized.png"

    _gradient(src, size)
    enc = encode_image_to_timeline(
        src, timeline, size=size, coding=coding, frame_ms=20.0, bit_depth=8
    )
    img, _ = prepare_image(src, size=size)
    img.save(resized)

    simulate_timeline(timeline, signal, sample_hz=200.0)
    dec = decode_signal_to_image(signal, out, frame_ms=20.0, coding=coding)

    assert dec["crc_ok"] is True
    assert enc["crc32"] == dec["crc32_got"]
    assert mae_images(resized, out) < 1.0


def test_preamble_constant():
    assert len(PREAMBLE_BITS) == 16
    assert PREAMBLE_BITS[:8] == (1, 0, 1, 0, 1, 0, 1, 0)


def test_encode_bits_roundtrip():
    bits = bytes_to_bits(b"FlashFrame!")
    for coding in ("manchester", "pwm"):
        sym = encode_bits(bits, coding)
        back = decode_bits(sym, coding)
        assert bits_to_bytes(back, len(b"FlashFrame!")) == b"FlashFrame!"
