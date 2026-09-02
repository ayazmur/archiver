"""Creates the Windows icon used by the app and PyInstaller build."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

SIZE = 256


def pixel(x: int, y: int) -> tuple[int, int, int, int]:
    # Navy-to-indigo rounded app tile.
    corner = 25
    if ((x < corner and y < corner and (x - corner) ** 2 + (y - corner) ** 2 > corner ** 2) or
            (x > SIZE - 1 - corner and y < corner and (x - (SIZE - 1 - corner)) ** 2 + (y - corner) ** 2 > corner ** 2) or
            (x < corner and y > SIZE - 1 - corner and (x - corner) ** 2 + (y - (SIZE - 1 - corner)) ** 2 > corner ** 2) or
            (x > SIZE - 1 - corner and y > SIZE - 1 - corner and (x - (SIZE - 1 - corner)) ** 2 + (y - (SIZE - 1 - corner)) ** 2 > corner ** 2)):
        return 0, 0, 0, 0
    blue = 38 + int(35 * y / SIZE)
    red = 28 + int(18 * y / SIZE)
    green = 80 + int(18 * x / SIZE)
    # Lock sits above the archive layers so it remains visible at small sizes.
    if 147 <= x <= 203 and 137 <= y <= 197:
        if 155 <= x <= 195 and 145 <= y <= 189:
            if 169 <= x <= 177 and 160 <= y <= 179:
                return 82, 65, 30, 255
            return 249, 201, 81, 255
        return 223, 170, 45, 255
    if 155 <= x <= 195 and 113 <= y <= 151:
        distance = (x - 175) ** 2 + (y - 136) ** 2
        if 14 ** 2 <= distance <= 22 ** 2:
            return 249, 201, 81, 255
    # Archive box: three bright horizontal layers.
    if 40 <= x <= 207 and 71 <= y <= 185:
        if y < 99:
            return 103, 213, 255, 255
        if y < 129:
            return 65, 191, 247, 255
        if y < 158:
            return 43, 159, 231, 255
        return 30, 121, 211, 255
    # Zip seam and pull tab.
    if 117 <= x <= 130 and 82 <= y <= 170:
        return 220, 248, 255, 255
    if 111 <= x <= 136 and 173 <= y <= 183:
        return 220, 248, 255, 255
    return red, green, blue, 255


def png() -> bytes:
    raw = bytearray()
    for y in range(SIZE):
        raw.append(0)
        for x in range(SIZE):
            raw.extend(pixel(x, y))
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")


image = png()
ico = struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(image), 22) + image
Path(__file__).parents[1].joinpath("assets", "app.ico").write_bytes(ico)
