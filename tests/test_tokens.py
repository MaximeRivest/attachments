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

#: Anthropic's own table (docs.claude.com vision page, "Resolution and token
#: cost", read 2026-10-09): size -> (standard tier, high-resolution tier).
ANTHROPIC_TABLE = [
    ((200, 200), 64, 64),
    ((1000, 1000), 1296, 1296),
    ((1092, 1092), 1521, 1521),
    ((1920, 1080), 1560, 2691),
    ((2000, 1500), 1564, 3888),
    ((3840, 2160), 1560, 4784),
]


@pytest.mark.parametrize(("size", "standard", "high"), ANTHROPIC_TABLE)
def test_image_tokens_match_anthropics_table(size, standard, high):
    assert image_tokens(*size, tier="standard") == standard
    assert image_tokens(*size) == high  # high is the default


def test_image_tokens_edge_cases():
    assert image_tokens(0, 10) == 0
    assert image_tokens(10, 2) == 1  # one partial patch
    with pytest.raises(ValueError, match="tier"):
        image_tokens(10, 10, tier="huge")


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
    # 1000 x 750: 36 x 27 patches of 28 px
    assert a.estimate_tokens() == {"text": 2, "images": 972, "total": 974}
    assert estimate_tokens(a.to_wire()) == a.estimate_tokens()
    assert a.tokens == 974


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
    assert a.estimate_tokens()["images"] == 4784  # the most a picture costs
    assert a.estimate_tokens(tier="standard")["images"] == 1568


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
    # each page 2000 x 1125 px: 72 x 41 patches on the high tier
    assert estimate["images"] == 2 * 2952
    assert estimate["total"] == estimate["text"] + 5904
    assert "(images ~5.9k)" in repr(a)
    assert a.estimate_tokens(tier="standard")["images"] == 2 * 1560
