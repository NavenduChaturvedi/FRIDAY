"""Generate assets/friday.ico — a cyan ring on a dark tile. Pure stdlib.

    python scripts/make_icon.py

Run once; the .ico is committed. Re-run only to change the mark.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

BG = (0x0B, 0x0E, 0x14, 0xFF)      # near-black tile
RING = (0x39, 0xC5, 0xCF, 0xFF)    # FRIDAY cyan
SIZES = (16, 32, 48, 256)


def _px(x: int, y: int, n: int) -> tuple[int, int, int, int]:
    cx = cy = (n - 1) / 2
    dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
    outer = n * 0.42
    inner = n * 0.42 - max(1.5, n * 0.11)
    if inner <= dist <= outer:
        # soft edge over ~1px
        edge = min(dist - inner, outer - dist)
        a = max(0.0, min(1.0, edge))
        return (
            round(BG[0] + (RING[0] - BG[0]) * a),
            round(BG[1] + (RING[1] - BG[1]) * a),
            round(BG[2] + (RING[2] - BG[2]) * a),
            0xFF,
        )
    return BG


def _png(n: int) -> bytes:
    raw = bytearray()
    for y in range(n):
        raw.append(0)  # filter: none
        for x in range(n):
            raw.extend(_px(x, y, n))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def _ico(pngs: list[tuple[int, bytes]]) -> bytes:
    out = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    for n, data in pngs:
        out += struct.pack(
            "<BBBBHHII", n & 0xFF, n & 0xFF, 0, 0, 1, 32, len(data), offset
        )
        offset += len(data)
    return out + b"".join(data for _, data in pngs)


def main() -> None:
    dest = Path(__file__).resolve().parent.parent / "assets" / "friday.ico"
    dest.parent.mkdir(exist_ok=True)
    dest.write_bytes(_ico([(n, _png(n)) for n in SIZES]))
    print(f"wrote {dest} ({dest.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
