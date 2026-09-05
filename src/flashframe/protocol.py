"""FlashFrame optical flash protocol constants and bit packing."""

from __future__ import annotations

import struct
import zlib
from typing import Literal

# Identity
MAGIC = b"FF"  # FlashFrame
VERSION = 1

# Defaults
DEFAULT_SIZE = 32
DEFAULT_BIT_DEPTH = 8  # bits per grayscale pixel
DEFAULT_FRAME_MS = 40  # duration of one Manchester half-bit (or one PWM bit)
DEFAULT_CODING: Literal["manchester", "pwm"] = "manchester"

# Brightness levels written into timelines (0..1)
LEVEL_DARK = 0.0
LEVEL_BRIGHT = 1.0

# Preamble: unique on/off pattern (raw brightness symbols at FRAME_MS each —
# NOT Manchester-coded) so receivers can lock via template match.
# Pattern: 1 0 1 0 1 0 1 0  1 1 1 1 0 0 0 0  (16 symbols)
PREAMBLE_BITS = (1, 0, 1, 0, 1, 0, 1, 0, 1, 1, 1, 1, 0, 0, 0, 0)

# Header layout (after preamble), packed then Manchester/PWM coded:
#   magic[2] version[1] width[1] height[1] bit_depth[1] coding[1] crc32[4]
# = 11 bytes
HEADER_BYTES = 11

CODING_MANCHESTER = 0
CODING_PWM = 1

CodingName = Literal["manchester", "pwm"]


def coding_to_int(coding: CodingName) -> int:
    return CODING_MANCHESTER if coding == "manchester" else CODING_PWM


def int_to_coding(v: int) -> CodingName:
    return "manchester" if v == CODING_MANCHESTER else "pwm"


def checksum32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def pack_header(
    width: int,
    height: int,
    bit_depth: int,
    coding: CodingName,
    crc: int,
) -> bytes:
    if not (1 <= width <= 255 and 1 <= height <= 255):
        raise ValueError("width/height must be 1..255 for v1 header")
    if bit_depth not in (1, 2, 4, 8):
        raise ValueError("bit_depth must be 1, 2, 4, or 8")
    return MAGIC + struct.pack(
        ">BBBBBI",
        VERSION,
        width,
        height,
        bit_depth,
        coding_to_int(coding),
        crc,
    )


def unpack_header(data: bytes) -> tuple[int, int, int, CodingName, int]:
    """Return (width, height, bit_depth, coding, crc)."""
    if len(data) < HEADER_BYTES or data[:2] != MAGIC:
        raise ValueError("invalid FlashFrame header / magic")
    version, width, height, bit_depth, coding_i, crc = struct.unpack(
        ">BBBBBI", data[2:HEADER_BYTES]
    )
    if version != VERSION:
        raise ValueError(f"unsupported protocol version {version}")
    if bit_depth not in (1, 2, 4, 8):
        raise ValueError(f"unsupported bit_depth {bit_depth}")
    return width, height, bit_depth, int_to_coding(coding_i), crc


def quantize_pixel(value: int, bit_depth: int) -> int:
    """Quantize 0..255 grayscale to bit_depth bits (returned as 0..(2^d-1))."""
    levels = 1 << bit_depth
    if bit_depth == 8:
        return max(0, min(255, int(value)))
    return max(0, min(levels - 1, int(round(value * (levels - 1) / 255.0))))


def dequantize_pixel(value: int, bit_depth: int) -> int:
    """Expand quantized pixel back to 0..255."""
    levels = 1 << bit_depth
    if bit_depth == 8:
        return max(0, min(255, int(value)))
    return int(round(value * 255.0 / (levels - 1)))


def pixels_to_bits(pixels: bytes, bit_depth: int) -> list[int]:
    """Pack pixel values into a MSB-first bit list."""
    bits: list[int] = []
    for p in pixels:
        q = quantize_pixel(p, bit_depth)
        for i in range(bit_depth - 1, -1, -1):
            bits.append((q >> i) & 1)
    return bits


def bits_to_pixels(bits: list[int], n_pixels: int, bit_depth: int) -> bytes:
    """Unpack MSB-first bits into n_pixels bytes (0..255)."""
    need = n_pixels * bit_depth
    if len(bits) < need:
        raise ValueError(f"not enough bits: got {len(bits)} need {need}")
    out = bytearray()
    idx = 0
    for _ in range(n_pixels):
        q = 0
        for _ in range(bit_depth):
            q = (q << 1) | bits[idx]
            idx += 1
        out.append(dequantize_pixel(q, bit_depth))
    return bytes(out)


def bytes_to_bits(data: bytes) -> list[int]:
    bits: list[int] = []
    for b in data:
        for i in range(7, -1, -1):
            bits.append((b >> i) & 1)
    return bits


def bits_to_bytes(bits: list[int], n_bytes: int) -> bytes:
    need = n_bytes * 8
    if len(bits) < need:
        raise ValueError(f"not enough bits: got {len(bits)} need {need}")
    out = bytearray()
    idx = 0
    for _ in range(n_bytes):
        v = 0
        for _ in range(8):
            v = (v << 1) | bits[idx]
            idx += 1
        out.append(v)
    return bytes(out)


def manchester_encode(bits: list[int]) -> list[int]:
    """Manchester: 0 → 1 then 0 (falling), 1 → 0 then 1 (rising)."""
    symbols: list[int] = []
    for b in bits:
        if b:
            symbols.extend((0, 1))
        else:
            symbols.extend((1, 0))
    return symbols


def manchester_decode(symbols: list[int]) -> list[int]:
    """Decode Manchester symbol pairs back to bits."""
    if len(symbols) % 2 != 0:
        symbols = symbols[:-1]
    bits: list[int] = []
    for i in range(0, len(symbols), 2):
        a, b = symbols[i], symbols[i + 1]
        if a == 0 and b == 1:
            bits.append(1)
        elif a == 1 and b == 0:
            bits.append(0)
        else:
            # Ambiguous — pick by majority / second half preference
            bits.append(1 if b >= a else 0)
    return bits


def pwm_encode(bits: list[int]) -> list[int]:
    """Simple OOK/PWM: one symbol per bit (bright=1, dark=0)."""
    return list(bits)


def pwm_decode(symbols: list[int]) -> list[int]:
    return [1 if s else 0 for s in symbols]


def encode_bits(bits: list[int], coding: CodingName) -> list[int]:
    if coding == "manchester":
        return manchester_encode(bits)
    return pwm_encode(bits)


def decode_bits(symbols: list[int], coding: CodingName) -> list[int]:
    if coding == "manchester":
        return manchester_decode(symbols)
    return pwm_decode(symbols)
