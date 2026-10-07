"""Tests for attachments._imagesize: header sizes agree with Pillow.

Covers every container variant the processors emit or pass through:
PNG, baseline and progressive JPEG (with a large EXIF block before the
frame header), GIF, WebP lossy (VP8), lossless (VP8L) and extended
(VP8X, with alpha), BMP (bottom-up and top-down), and malformed data.
"""

from __future__ import annotations

import io
import random

import pytest

from attachments._imagesize import image_size
from attachments.deps import check_dep

pytestmark = pytest.mark.skipif(
    not check_dep("image").available, reason="Pillow needed"
)

SIZES = [(1, 1), (7, 3), (640, 480), (1568, 882), (3001, 17), (16383, 2)]

VARIANTS = [
    ("PNG", "RGBA", {}),
    ("JPEG", "RGB", {}),
    ("JPEG", "RGB", {"progressive": True, "exif": b"Exif\x00\x00" + b"x" * 20000}),
    ("JPEG", "L", {}),
    ("GIF", "RGB", {}),
    ("WEBP", "RGB", {"quality": 50}),
    ("WEBP", "RGB", {"lossless": True}),
    ("WEBP", "RGBA", {"quality": 80}),  # alpha -> VP8X container
    ("BMP", "RGB", {}),
]


def _encode(fmt: str, mode: str, size: tuple[int, int], options: dict) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new(mode, size, "white").save(buf, format=fmt, **options)
    return buf.getvalue()


@pytest.mark.parametrize("fmt, mode, options", VARIANTS)
@pytest.mark.parametrize("size", SIZES)
def test_header_size_matches_pillow(fmt, mode, options, size):
    from PIL import Image

    data = _encode(fmt, mode, size, options)
    assert image_size(data) == Image.open(io.BytesIO(data)).size


def test_top_down_bmp_reports_positive_height():
    data = bytearray(_encode("BMP", "RGB", (5, 4), {}))
    data[22:26] = (-4).to_bytes(4, "little", signed=True)
    assert image_size(bytes(data)) == (5, 4)


@pytest.mark.parametrize("fmt, mode, options", VARIANTS)
def test_truncated_or_corrupt_data_never_raises(fmt, mode, options):
    data = _encode(fmt, mode, (300, 200), options)
    rng = random.Random(0)
    for cut in (1, 5, 11, 20, 29, len(data) // 2):
        image_size(data[:cut])  # None or a size, never an exception
    for _ in range(50):
        noisy = bytearray(data)
        for _ in range(8):
            noisy[rng.randrange(len(noisy))] = rng.randrange(256)
        image_size(bytes(noisy))


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\x89PNG\r\n\x1a\n",
        b"\xff\xd8\xff",
        b"RIFF\x00\x00\x00\x00WEBPXXXX",
        b"<svg/>",
    ],
)
def test_unknown_or_incomplete_headers_return_none(data):
    assert image_size(data) is None
