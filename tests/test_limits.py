"""Requests that a provider would reject warn, with the fix, when built."""

from __future__ import annotations

import base64
import io
import struct
import warnings
import zlib

import pytest

from attachments import Artifacts, RequestLimitWarning
from attachments.render import to_claude_messages, to_openai_messages
from attachments.types import make_artifact


def _png_header(width: int, height: int, padding: int = 0) -> bytes:
    """A PNG whose header says width x height (enough for the size check)."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    chunk = struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr
    chunk += struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))
    return b"\x89PNG\r\n\x1a\n" + chunk + b"\0" * padding


def _artifact(*images: bytes, mimetype: str = "image/png") -> dict:
    return make_artifact(
        text="page text",
        images=[
            {"name": f"p{i}.png", "mimetype": mimetype, "bytes": b}
            for i, b in enumerate(images)
        ],
        meta={"source": "doc.pdf"},
    )


def _warnings(build) -> list[warnings.WarningMessage]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        build()
    return [w for w in caught if issubclass(w.category, RequestLimitWarning)]


class TestClaude:
    def test_a_fitting_request_is_quiet(self):
        assert (
            _warnings(lambda: to_claude_messages([_artifact(_png_header(800, 1000))]))
            == []
        )

    def test_over_32_mb_names_the_size_and_the_fix(self):
        big = [_png_header(1500, 2000, padding=2_000_000) for _ in range(13)]
        (w,) = _warnings(lambda: to_claude_messages([_artifact(*big)]))
        message = str(w.message)
        assert "would be rejected" in message
        assert "Claude accepts 32.0 MB" in message and "Bedrock: 20 MB" in message
        assert "image_format: jpeg" in message  # mostly PNG
        assert "pages: 1-6" in message

    def test_too_many_pictures(self):
        small = [_png_header(100, 100) for _ in range(101)]
        (w,) = _warnings(lambda: to_claude_messages([_artifact(*small)]))
        assert "101 pictures; Claude accepts 100" in str(w.message)
        assert "600 for others" in str(w.message)

    def test_one_picture_over_10_mb(self):
        (w,) = _warnings(
            lambda: to_claude_messages([_artifact(_png_header(900, 900, 8_000_000))])
        )
        assert "a picture is 10.7 MB (base64); Claude accepts 10.0 MB" in str(w.message)

    def test_more_than_20_pictures_must_be_2000_px_at_most(self):
        pictures = [_png_header(1000, 1000) for _ in range(20)] + [
            _png_header(2400, 1800)
        ]
        (w,) = _warnings(lambda: to_claude_messages([_artifact(*pictures)]))
        assert "up to 2400x1800 px" in str(w.message)
        assert "2000 px a side when a request has more than 20" in str(w.message)
        # 20 pictures: the general 8000 px limit applies
        assert _warnings(lambda: to_claude_messages([_artifact(*pictures[1:])])) == []

    def test_unsupported_format(self):
        (w,) = _warnings(
            lambda: to_claude_messages([_artifact(b"BM....", mimetype="image/bmp")])
        )
        assert "image/bmp" in str(w.message) and "image_format: png" in str(w.message)

    def test_warning_points_at_the_callers_line(self):
        big = [_png_header(1500, 2000, padding=2_000_000) for _ in range(13)]
        a = Artifacts([_artifact(*big)])
        (w,) = _warnings(lambda: a.claude("Summarize."))
        assert w.filename == __file__

    def test_wire_form_artifacts_are_checked_too(self):
        big = _png_header(900, 900, 8_000_000)
        wire = Artifacts([_artifact(big)]).to_wire()
        assert _warnings(lambda: to_claude_messages(Artifacts.from_wire(wire)))

    def test_can_be_silenced(self):
        big = [_png_header(100, 100) for _ in range(101)]
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            warnings.filterwarnings("ignore", category=RequestLimitWarning)
            to_claude_messages([_artifact(*big)])


class TestOpenAI:
    def test_large_request_fits_openai(self):
        big = [_png_header(1500, 2000, padding=2_000_000) for _ in range(13)]
        assert _warnings(lambda: to_openai_messages([_artifact(*big)])) == []

    def test_unsupported_format(self):
        (w,) = _warnings(
            lambda: to_openai_messages([_artifact(b"BM....", mimetype="image/bmp")])
        )
        assert "OpenAI request would be rejected" in str(w.message)


def test_scanned_pdf_fits_claude_by_default(tmp_path):
    """The case that motivated this: 20 scanned pages, default options."""
    pymupdf = pytest.importorskip("pymupdf")
    import numpy as np
    from PIL import Image

    from attachments import att

    rng = np.random.default_rng(0)
    doc = pymupdf.open()
    for _ in range(20):
        noise = (225 + rng.normal(0, 9, (1100, 850))).clip(0, 255).astype("uint8")
        buffer = io.BytesIO()
        Image.fromarray(noise).convert("RGB").save(buffer, "JPEG", quality=75)
        page = doc.new_page(width=612, height=792)
        page.insert_image(page.rect, stream=buffer.getvalue())
    path = tmp_path / "scan.pdf"
    doc.save(path)

    a = att(f"{path}[ocr: false]")
    assert {im["mimetype"] for im in a.images} == {"image/jpeg"}
    assert _warnings(lambda: a.claude("Summarize.")) == []
    request = sum(len(base64.b64encode(im["bytes"])) for im in a.images)
    assert request < 32_000_000
