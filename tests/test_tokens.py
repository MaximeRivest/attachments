"""Tests for the token estimate: text and images.

Covers:
    - image_tokens: Anthropic's rule (shrink to 1568 px, at most ~1,600)
    - estimate_tokens on real encoded images of every format the
      processors emit, in-process and wire form
    - Unknown image sizes count as the maximum (a safe upper bound)
    - Artifacts.tokens / estimate_tokens / repr include images
    - A real 2-page slide-sized PDF render (the review's sample case)
"""

from __future__ import annotations

import io

import pytest

from attachments import Artifacts, att, estimate_tokens
from attachments.deps import check_dep
from attachments.render import image_tokens
from attachments.types import make_artifact


@pytest.mark.parametrize(
    "size, expected",
    [
        ((100, 75), 10),  # small: plain width*height/750
        ((1092, 1092), 1590),  # Anthropic's published 1:1 maximum
        ((1568, 882), 1600),  # within the edge but over ~1,600: capped
        ((2667, 1500), 1600),  # 200 dpi 16:9 page
        ((4000, 100), 82),  # edge rule only: 1568 x 39.2 = 61,466 px
        ((0, 10), 0),
    ],
)
def test_image_tokens(size, expected):
    assert image_tokens(*size) == expected


def _encoded(fmt: str, size: tuple[int, int]) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, format=fmt)
    return buf.getvalue()


@pytest.mark.skipif(not check_dep("image").available, reason="Pillow needed")
@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "GIF", "WEBP", "BMP"])
def test_estimate_reads_each_format_in_process_and_wire(fmt):
    payload = _encoded(fmt, (1000, 750))
    a = Artifacts(
        [
            make_artifact(
                text="x" * 8,
                images=[{"name": "i", "mimetype": "image/x", "bytes": payload}],
                meta={"source": "i"},
            )
        ]
    )
    assert a.estimate_tokens() == {"text": 2, "images": 1000, "total": 1002}
    assert estimate_tokens(a.to_wire()) == a.estimate_tokens()
    assert a.tokens == 1002


def test_unreadable_image_counts_as_the_maximum_and_missing_payload_as_zero():
    a = Artifacts(
        [
            make_artifact(
                images=[
                    {"name": "x.svg", "mimetype": "image/svg+xml", "bytes": b"<svg/>"},
                    {"name": "ghost.png", "mimetype": "image/png"},
                ],
                meta={"source": "x"},
            )
        ]
    )
    assert a.estimate_tokens()["images"] == 1600


def test_text_only_estimate_is_unchanged():
    a = Artifacts([make_artifact(text="abcde", meta={"source": "a"})])
    assert a.estimate_tokens() == {"text": 2, "images": 0, "total": 2}
    assert repr(a) == "<Artifacts: 1 artifact | 5 chars | ~2 tokens>"


@pytest.mark.skipif(not check_dep("pdf-images").available, reason="PyMuPDF needed")
def test_two_slide_sized_pages_estimate(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    for _ in range(2):
        doc.new_page(width=960, height=540).insert_text((72, 72), "slide")
    path = tmp_path / "deck.pdf"
    doc.save(path)
    doc.close()

    a = att(f"{path}[images: true]")
    estimate = a.estimate_tokens()
    assert estimate["images"] == 3200  # 2 pages, each at the ~1,600 cap
    assert estimate["total"] == estimate["text"] + 3200
    assert "(images ~3.2k)" in repr(a)
