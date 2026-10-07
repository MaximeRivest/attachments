"""Read an image's pixel size from its header, standard library only.

The token estimate needs each image's width and height. Decoding with
Pillow would add a dependency to the core and cost a full decode; every
format the processors emit stores its size in the first bytes (JPEG: in
the frame header after any metadata segments), so a few struct reads
suffice.

Covered: PNG, JPEG (baseline and progressive), GIF, WebP (lossy,
lossless, extended) and BMP — everything the image, pdf, pptx, docx,
html and ipynb processors pass through. Anything else returns ``None``
and callers choose a fallback.
"""

from __future__ import annotations

import struct

__all__ = ["image_size"]

#: JPEG start-of-frame markers that carry the frame size (C4, C8 and CC
#: are DHT/JPG/DAC, which do not).
_JPEG_SOF = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
)


def _png(data: bytes) -> tuple[int, int] | None:
    if len(data) >= 24 and data[12:16] == b"IHDR":
        return struct.unpack(">II", data[16:24])
    return None


def _gif(data: bytes) -> tuple[int, int] | None:
    if len(data) >= 10:
        return struct.unpack("<HH", data[6:10])
    return None


def _jpeg(data: bytes) -> tuple[int, int] | None:
    i, n = 2, len(data)
    while i + 4 <= n:
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:  # no length
            i += 2
            continue
        (length,) = struct.unpack(">H", data[i + 2 : i + 4])
        if marker in _JPEG_SOF:
            if i + 9 > n:
                return None
            height, width = struct.unpack(">HH", data[i + 5 : i + 9])
            return width, height
        if marker in (0xD9, 0xDA):  # end of image / start of scan
            return None
        i += 2 + length
    return None


def _webp(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30:
        return None
    chunk = data[12:16]
    if chunk == b"VP8 ":
        width, height = struct.unpack("<HH", data[26:30])
        return width & 0x3FFF, height & 0x3FFF
    if chunk == b"VP8L":
        b = data[21:25]
        width = 1 + (((b[1] & 0x3F) << 8) | b[0])
        height = 1 + (((b[3] & 0x0F) << 10) | (b[2] << 2) | ((b[1] & 0xC0) >> 6))
        return width, height
    if chunk == b"VP8X":
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height
    return None


def _bmp(data: bytes) -> tuple[int, int] | None:
    if len(data) < 26:
        return None
    (header_size,) = struct.unpack("<I", data[14:18])
    if header_size == 12:  # OS/2 BITMAPCOREHEADER
        return struct.unpack("<HH", data[18:22])
    width, height = struct.unpack("<ii", data[18:26])
    return abs(width), abs(height)  # negative height = top-down rows


def image_size(data: bytes) -> tuple[int, int] | None:
    """Return ``(width, height)`` in pixels, or ``None`` when unknown.

    Never raises: truncated or unrecognized data returns ``None``.

    Examples:
        >>> png = bytes.fromhex(
        ...     "89504e470d0a1a0a0000000d49484452000002000000010008060000001f15c489"
        ... )
        >>> image_size(png)
        (512, 256)
        >>> image_size(b"GIF89a\\x10\\x00\\x20\\x00")
        (16, 32)
        >>> image_size(b"not an image") is None
        True
        >>> image_size(b"") is None
        True
    """
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            size = _png(data)
        elif data[:3] == b"\xff\xd8\xff":
            size = _jpeg(data)
        elif data[:6] in (b"GIF87a", b"GIF89a"):
            size = _gif(data)
        elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            size = _webp(data)
        elif data[:2] == b"BM":
            size = _bmp(data)
        else:
            size = None
    except (struct.error, IndexError):
        return None
    if size is None or size[0] <= 0 or size[1] <= 0:
        return None
    return int(size[0]), int(size[1])
