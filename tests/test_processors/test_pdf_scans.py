"""Scanned pages in PDFs: decided page by page.

A page with no text layer gets OCR and a picture (``images: auto``), even
inside an otherwise typed document; blank pages get neither; a page that
is mostly a picture is delivered as JPEG, the rest as PNG; automatic OCR
stops at ``AUTO_OCR_MAX_PAGES``. OCR is a stand-in here (fast, exact);
tests/test_ocr.py runs the real engine.
"""

from __future__ import annotations

import io
import sys

import pytest

from attachments import att
from attachments._imagesize import image_size
from attachments._processors import _ocr, pdf
from attachments._processors.pdf import process_pdf

pymupdf = pytest.importorskip("pymupdf")


def _photo(width=170, height=220) -> bytes:
    """A grey, scan-like JPEG."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (225, 222, 215)).save(buffer, "JPEG")
    return buffer.getvalue()


def _pdf(*kinds: str) -> bytes:
    """Pages: "text" (a text layer), "scan" (one picture, the whole page),
    "blank", or "drawing" (vector lines, no text)."""
    doc = pymupdf.open()
    for n, kind in enumerate(kinds, 1):
        page = doc.new_page(width=612, height=792)
        if kind == "text":
            page.insert_text((72, 72), f"Typed text on page {n}")
        elif kind == "scan":
            page.insert_image(page.rect, stream=_photo())
        elif kind == "drawing":
            page.draw_rect(pymupdf.Rect(100, 100, 400, 300))
    return doc.tobytes()


@pytest.fixture
def mask_modules(monkeypatch):
    """Hide modules from the import machinery (test_missing_deps pattern)."""
    from attachments.deps import clear_cache

    def _mask(*names: str) -> None:
        for name in names:
            monkeypatch.setitem(sys.modules, name, None)
        clear_cache()

    yield _mask
    clear_cache()


@pytest.fixture
def fake_ocr(monkeypatch):
    """OCR stand-in: 'OCR text' plus the picture size; records calls."""
    seen: list[tuple[int, int]] = []

    def recognize(picture) -> _ocr.OcrText:
        seen.append(picture.size)
        return _ocr.OcrText(f"OCR text {len(seen)}", 0.99)

    monkeypatch.setattr(_ocr, "recognize", recognize)
    monkeypatch.setattr(
        "attachments.deps.check_dep",
        lambda name: type("S", (), {"available": True, "missing": []})(),
    )
    return seen


def _pages(result: dict) -> dict[int, str]:
    text = result["text"]
    return {s["page"]: text[s["start"] : s["end"]] for s in result["meta"]["segments"]}


class TestPageByPage:
    def test_scanned_pages_inside_a_typed_document(self, fake_ocr):
        result = process_pdf(_pdf("text", "scan", "text", "blank", "scan"))
        pages = _pages(result)
        assert pages[1] == "Typed text on page 1"
        assert pages[2] == "OCR text 1"
        assert pages[3] == "Typed text on page 3"
        assert pages[4] == ""  # blank: not read
        assert pages[5] == "OCR text 2"
        assert len(fake_ocr) == 2
        assert [im["page"] for im in result["images"]] == [2, 5]  # images: auto
        assert result["meta"]["extra"]["ocr_pages"] == [2, 5]

    def test_typed_document_is_untouched(self, fake_ocr):
        data = _pdf("text", "text")
        result = process_pdf(data)
        assert fake_ocr == [] and result["images"] == []
        assert "ocr" not in result["meta"]["extra"]

    def test_drawing_without_text_is_read_and_pictured(self, fake_ocr):
        result = process_pdf(_pdf("drawing"))
        assert result["text"] == "OCR text 1"
        assert result["images"][0]["mimetype"] == "image/png"  # lines, not photo

    def test_same_file_same_output(self, fake_ocr):
        data = _pdf("scan", "text", "scan")
        first, second = process_pdf(data), process_pdf(data)
        assert first["images"] == second["images"]
        assert first["meta"]["segments"] == second["meta"]["segments"]


class TestPictureFormat:
    def test_auto_is_jpeg_for_scans_and_png_for_text(self, fake_ocr):
        result = process_pdf(_pdf("scan", "text"), render_images=True)
        kinds = {im["page"]: im["mimetype"] for im in result["images"]}
        assert kinds == {1: "image/jpeg", 2: "image/png"}
        assert result["images"][0]["name"].endswith("-page-1.jpg")

    def test_auto_without_ocr(self):
        result = process_pdf(_pdf("scan", "text"), render_images=True, ocr=False)
        kinds = {im["page"]: im["mimetype"] for im in result["images"]}
        assert kinds == {1: "image/jpeg", 2: "image/png"}

    @pytest.mark.parametrize("fmt", ["png", "jpeg"])
    def test_a_chosen_format_applies_to_every_page(self, fake_ocr, fmt):
        result = process_pdf(_pdf("scan", "text"), render_images=True, image_format=fmt)
        assert {im["mimetype"] for im in result["images"]} == {f"image/{fmt}"}

    def test_picture_made_with_ocr_has_the_size_of_a_direct_one(self, fake_ocr):
        data = _pdf("scan")
        with_ocr = process_pdf(data, max_dim=800)["images"][0]
        without = process_pdf(data, max_dim=800, ocr=False)["images"][0]
        assert image_size(with_ocr["bytes"]) == image_size(without["bytes"])
        assert fake_ocr == [(1700, 2200)]  # OCR reads the page at 200 dpi

    def test_option_is_checked(self):
        result = process_pdf(_pdf("scan"), image_format="gif")
        assert result["meta"]["error"]["code"] == "invalid-option"
        assert "auto, png or jpeg" in result["meta"]["error"]["message"]


class TestAutomaticOcrLimit:
    def test_auto_stops_and_says_how_to_read_the_rest(self, fake_ocr, monkeypatch):
        monkeypatch.setattr(pdf, "AUTO_OCR_MAX_PAGES", 2)
        result = process_pdf(_pdf("scan", "scan", "text", "scan"))
        assert len(fake_ocr) == 2
        assert _pages(result)[4] == ""
        (warning,) = result["meta"]["warnings"]
        assert "first 2 of 3 pages without text" in warning
        assert "[ocr: true]" in warning and "[pages: 4-]" in warning
        assert [im["page"] for im in result["images"]] == [1, 2, 4]  # all pictured

    def test_forced_ocr_reads_every_page(self, fake_ocr, monkeypatch):
        monkeypatch.setattr(pdf, "AUTO_OCR_MAX_PAGES", 2)
        result = process_pdf(_pdf("scan", "scan", "scan"), ocr=True)
        assert len(fake_ocr) == 3 and "warnings" not in result["meta"]

    def test_the_warning_shows_when_printed(self, fake_ocr, monkeypatch, tmp_path):
        monkeypatch.setattr(pdf, "AUTO_OCR_MAX_PAGES", 1)
        path = tmp_path / "scan.pdf"
        path.write_bytes(_pdf("scan", "scan"))
        assert "! scan.pdf: ocr: read the first 1 of 2" in repr(att(str(path)))


class TestOcrPageSettings:
    def test_ocr_auto_pages(self, fake_ocr):
        from attachments import configure, reset_config

        configure(ocr_auto_pages=1)
        try:
            result = process_pdf(_pdf("scan", "scan"))
        finally:
            reset_config()
        assert len(fake_ocr) == 1
        assert "automatic OCR stops there" in result["meta"]["warnings"][0]

    def test_ocr_max_pages_bounds_even_forced_ocr(self, fake_ocr, monkeypatch):
        monkeypatch.setenv("ATTACHMENTS_OCR_MAX_PAGES", "2")
        result = process_pdf(_pdf("scan", "scan", "scan"), ocr=True)
        assert len(fake_ocr) == 2
        (warning,) = result["meta"]["warnings"]
        assert "the most OCR reads where this ran: ocr_max_pages" in warning
        assert "[pages: 3-] reads the rest" in warning
        assert "[ocr: true]" not in warning

    def test_ocr_max_pages_lowers_automatic_ocr(self, fake_ocr, monkeypatch):
        monkeypatch.setenv("ATTACHMENTS_OCR_MAX_PAGES", "1")
        result = process_pdf(_pdf("scan", "scan"))
        assert len(fake_ocr) == 1
        (warning,) = result["meta"]["warnings"]
        assert "first 1 of 2" in warning and "ocr_max_pages" in warning
        assert "[ocr: true]" not in warning  # it would not help here
        assert "[pages: 2-] reads the rest" in warning


class TestTurnedPages:
    def test_picture_of_a_turned_page_is_delivered_upright(self, monkeypatch):
        monkeypatch.setattr(
            _ocr, "recognize", lambda picture: _ocr.OcrText("sideways text", 0.99, 90)
        )
        monkeypatch.setattr(
            "attachments.deps.check_dep",
            lambda name: type("S", (), {"available": True, "missing": []})(),
        )
        result = process_pdf(_pdf("scan"), max_dim=1000)
        width, height = image_size(result["images"][0]["bytes"])
        assert width > height  # portrait page, turned a quarter
        assert result["meta"]["extra"]["ocr_turned"] == {"1": 90}


class TestFailures:
    def test_engine_failure_is_a_processing_error(self, monkeypatch):
        def broken(picture):
            raise RuntimeError("model file damaged")

        monkeypatch.setattr(_ocr, "recognize", broken)
        monkeypatch.setattr(
            "attachments.deps.check_dep",
            lambda name: type("S", (), {"available": True, "missing": []})(),
        )
        result = process_pdf(_pdf("scan"))
        assert result["meta"]["error"]["code"] == "processing-error"
        assert "model file damaged" in result["meta"]["error"]["message"]

    def test_missing_engine_gives_the_hint_for_mixed_documents(self, mask_modules):
        mask_modules("rapidocr")
        result = process_pdf(_pdf("text", "scan"))
        assert "pip install attachments[ocr]" in result["meta"]["note"]
        assert [im["page"] for im in result["images"]] == [2]  # still pictured

    def test_encrypted_scan_with_password(self, fake_ocr):
        doc = pymupdf.open(stream=_pdf("scan"), filetype="pdf")
        data = doc.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="secret"
        )
        result = process_pdf(data, password="secret")
        assert result["text"] == "OCR text 1" and len(result["images"]) == 1
