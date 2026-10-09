"""Remove what a photo says about its owner, without touching its pixels.

Phone and camera pictures carry metadata the model does not need and the
owner may not want to send: GPS location, date and time, camera serial
number, owner name, editing history, a thumbnail of the original. It is
cut out of the file directly, segment by segment, so the picture is not
decoded or re-compressed (no quality lost, no time spent). The colour
profile (ICC) stays: it changes how colours look, not who took the photo.

=====  ====================================================================
JPEG   drops APP1 (EXIF, XMP), APP3-APP13, APP15 (IPTC, maker data),
       comments, APP2 multi-picture data and anything after the end of
       the image (extra pictures, vendor trailers); keeps APP0 (JFIF),
       APP2 ICC profile, APP14 (Adobe colour transform, needed to decode)
PNG    drops eXIf, tEXt, zTXt, iTXt, tIME
WebP   drops EXIF and XMP chunks, clears their flags in VP8X
other  unchanged (GIF, BMP: no such metadata in practice)
=====  ====================================================================

Anything that does not parse as expected is returned unchanged: a picture
is never broken to remove metadata from it.
"""

from __future__ import annotations

import struct

#: JPEG segments kept: APP0 (JFIF), APP14 (Adobe); APP2 only for ICC.
_JPEG_KEEP = {0xE0, 0xEE}
_PNG_DROP = {b"eXIf", b"tEXt", b"zTXt", b"iTXt", b"tIME"}
_WEBP_DROP = {b"EXIF", b"XMP "}


def _jpeg(data: bytes) -> tuple[bytes, list[str]]:
    if data[:2] != b"\xff\xd8":
        return data, []
    out = bytearray(data[:2])
    removed: list[str] = []
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            return data, []  # not a marker where one must be: leave it
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker == 0xDA:  # start of scan: the picture itself follows
            end = _jpeg_end(data, i)
            if end is None:
                return data, []
            if end < len(data):
                removed.append("trailing data")
            out += data[i:end]
            return bytes(out), removed
        (length,) = struct.unpack(">H", data[i + 2 : i + 4])
        segment = data[i : i + 2 + length]
        if len(segment) < 2 + length:
            return data, []
        payload = segment[4:]
        if marker in _JPEG_KEEP or not 0xE0 <= marker <= 0xEF and marker != 0xFE:
            out += segment
        elif marker == 0xE2 and payload.startswith(b"ICC_PROFILE\0"):
            out += segment
        else:
            removed.append(_jpeg_name(marker, payload))
        i += 2 + length
    return data, []


def _jpeg_end(data: bytes, start: int) -> int | None:
    """Index just after the end-of-image marker that ends the picture.

    In compressed data a 0xFF byte is followed by 0x00 (stuffing) or a
    restart marker (D0-D7); scans of progressive JPEGs are separated by
    other markers, which are skipped by their length.
    """
    i = start
    while True:
        j = data.find(b"\xff", i)
        if j < 0 or j + 1 >= len(data):
            return None
        marker = data[j + 1]
        if marker == 0xD9:
            return j + 2
        if marker == 0x00 or 0xD0 <= marker <= 0xD7 or marker == 0xFF:
            i = j + 1
            continue
        # A marker segment between scans (DHT, DQT, SOS, ...): skip it.
        if j + 4 > len(data):
            return None
        (length,) = struct.unpack(">H", data[j + 2 : j + 4])
        i = j + 2 + length


def _jpeg_name(marker: int, payload: bytes) -> str:
    if marker == 0xE1:
        return "xmp" if payload.startswith(b"http://ns.adobe.com/xap") else "exif"
    if marker == 0xED:
        return "iptc"
    if marker == 0xFE:
        return "comment"
    return f"app{marker - 0xE0}"


def _png(data: bytes) -> tuple[bytes, list[str]]:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return data, []
    out = bytearray(data[:8])
    removed: list[str] = []
    i = 8
    while i + 12 <= len(data):
        (length,) = struct.unpack(">I", data[i : i + 4])
        kind = data[i + 4 : i + 8]
        chunk = data[i : i + 12 + length]
        if len(chunk) < 12 + length:
            return data, []
        if kind in _PNG_DROP:
            removed.append(kind.decode("ascii").lower())
        else:
            out += chunk
        i += 12 + length
        if kind == b"IEND":
            if i < len(data):
                removed.append("trailing data")
            return bytes(out), removed
    return data, []


def _webp(data: bytes) -> tuple[bytes, list[str]]:
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return data, []
    chunks: list[bytes] = []
    removed: list[str] = []
    i = 12
    while i + 8 <= len(data):
        kind = data[i : i + 4]
        (length,) = struct.unpack("<I", data[i + 4 : i + 8])
        size = 8 + length + (length & 1)  # chunks are padded to even sizes
        chunk = data[i : i + size]
        if len(chunk) < 8 + length:
            return data, []
        if kind in _WEBP_DROP:
            removed.append(kind.decode("ascii").strip().lower())
        else:
            chunks.append(chunk)
        i += size
    if not removed:
        return data, []
    body = bytearray(b"".join(chunks))
    if body[:4] == b"VP8X" and len(body) > 8:
        body[8] &= ~(0x08 | 0x04) & 0xFF  # EXIF and XMP present flags
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + bytes(body), removed


_BY_TYPE = {"image/jpeg": _jpeg, "image/png": _png, "image/webp": _webp}


def strip_metadata(data: bytes, mimetype: str) -> tuple[bytes, list[str]]:
    """*data* without personal metadata, and the kinds removed (sorted).

    Examples:
        >>> strip_metadata(b"GIF89a...", "image/gif")
        (b'GIF89a...', [])
        >>> strip_metadata(b"\\xff\\xd8 not really a jpeg", "image/jpeg")[1]
        []
    """
    strip = _BY_TYPE.get(mimetype)
    if strip is None:
        return data, []
    try:
        cleaned, removed = strip(data)
    except (struct.error, IndexError):
        return data, []
    return cleaned, sorted(set(removed))
