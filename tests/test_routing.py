"""Tests for magic-byte content detection and processor routing (VISION A3).

Covers:
    - utils.detect_extension unit behavior for every recognized signature,
      including OOXML zip discrimination and the BMP false-positive guard.
    - core._route_processor order: extension lookup, then content sniff
      (only when the sniffed extension has a registered processor), then
      the text heuristic fallback.
    - End-to-end routing through att() for extensionless real files.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from attachments import att
from attachments._processors import processors
from attachments.core import _route_processor
from attachments.utils import detect_extension

# =============================================================================
# Helpers
# =============================================================================


def make_zip(*names: str) -> bytes:
    """Build an in-memory zip containing the given member names."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in names:
            zf.writestr(name, "x")
    return buf.getvalue()


def make_real_pdf() -> bytes:
    """A real (blank-page) PDF built with pypdf."""
    pytest.importorskip("pypdf")
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def make_real_xlsx() -> bytes:
    """A real XLSX built with openpyxl."""
    pytest.importorskip("openpyxl")
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "People"
    ws.append(["Name", "Age"])
    ws.append(["Alice", 30])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# =============================================================================
# detect_extension: simple signatures
# =============================================================================


class TestDetectExtensionSignatures:
    def test_pdf(self):
        assert detect_extension(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3") == ".pdf"

    def test_pdf_requires_full_signature(self):
        assert detect_extension(b"%PDF") is None

    def test_real_pdf(self):
        assert detect_extension(make_real_pdf()) == ".pdf"

    def test_png(self):
        assert detect_extension(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8) == ".png"

    def test_real_png(self):
        pytest.importorskip("PIL")
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (2, 2), "red").save(buf, format="PNG")
        assert detect_extension(buf.getvalue()) == ".png"

    def test_jpeg(self):
        assert detect_extension(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00") == ".jpg"

    def test_jpeg_requires_third_byte(self):
        assert detect_extension(b"\xff\xd8\x00\x00") is None

    def test_gif87a(self):
        assert detect_extension(b"GIF87a" + b"\x00" * 10) == ".gif"

    def test_gif89a(self):
        assert detect_extension(b"GIF89a" + b"\x00" * 10) == ".gif"

    def test_gif_unknown_version_rejected(self):
        assert detect_extension(b"GIF99a" + b"\x00" * 10) is None

    def test_webp(self):
        data = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 16
        assert detect_extension(data) == ".webp"

    def test_riff_without_webp_rejected(self):
        # RIFF is also the WAV/AVI container — only WEBP maps to an image.
        data = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 16
        assert detect_extension(data) is None

    def test_empty_bytes(self):
        assert detect_extension(b"") is None

    def test_plain_text(self):
        assert detect_extension(b"Hello, world!\nJust text.\n") is None

    def test_arbitrary_binary(self):
        assert detect_extension(bytes(range(256))) is None


# =============================================================================
# detect_extension: BMP plausibility guard
# =============================================================================


class TestDetectExtensionBmp:
    def test_bmp_with_matching_size_header(self):
        payload_len = 30
        data = b"BM" + payload_len.to_bytes(4, "little") + b"\x00" * 24
        assert len(data) == payload_len
        assert detect_extension(data) == ".bmp"

    def test_bmp_with_zero_size_header(self):
        # Some encoders leave the size field zeroed; still plausible.
        data = b"BM" + b"\x00" * 28
        assert detect_extension(data) == ".bmp"

    def test_real_bmp_from_pillow(self):
        pytest.importorskip("PIL")
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (2, 2), "blue").save(buf, format="BMP")
        assert detect_extension(buf.getvalue()) == ".bmp"

    def test_bm_text_is_not_bmp(self):
        # "BM" prefix with an implausible size field must not match.
        data = b"BMW is a car maker, not a bitmap header at all"
        assert len(data) >= 26
        assert detect_extension(data) is None

    def test_short_bm_prefix_is_not_bmp(self):
        assert detect_extension(b"BM tiny") is None


# =============================================================================
# detect_extension: zip / OOXML discrimination
# =============================================================================


class TestDetectExtensionOoxml:
    def test_docx(self):
        data = make_zip("[Content_Types].xml", "word/document.xml", "_rels/.rels")
        assert detect_extension(data) == ".docx"

    def test_xlsx(self):
        data = make_zip("[Content_Types].xml", "xl/workbook.xml", "_rels/.rels")
        assert detect_extension(data) == ".xlsx"

    def test_pptx(self):
        data = make_zip("[Content_Types].xml", "ppt/presentation.xml", "_rels/.rels")
        assert detect_extension(data) == ".pptx"

    def test_real_xlsx_bytes(self):
        assert detect_extension(make_real_xlsx()) == ".xlsx"

    def test_plain_zip_is_none(self):
        # Plain archives are unpack's job, not a processor's.
        assert detect_extension(make_zip("hello.txt", "sub/dir.md")) is None

    def test_content_types_without_ooxml_directory_is_none(self):
        assert (
            detect_extension(make_zip("[Content_Types].xml", "other/part.xml")) is None
        )

    def test_corrupt_zip_is_none(self):
        assert detect_extension(b"PK\x03\x04 this is not a valid zip body") is None


# =============================================================================
# detect_extension: HTML sniffing
# =============================================================================


class TestDetectExtensionHtml:
    def test_doctype(self):
        assert detect_extension(b"<!doctype html><html></html>") == ".html"

    def test_doctype_uppercase(self):
        assert detect_extension(b"<!DOCTYPE HTML PUBLIC ...>") == ".html"

    def test_html_tag(self):
        assert detect_extension(b'<html lang="en"><body/></html>') == ".html"

    def test_html_tag_uppercase(self):
        assert detect_extension(b"<HTML><BODY></BODY></HTML>") == ".html"

    def test_leading_whitespace(self):
        assert detect_extension(b"   \n\t\r\n  <html><p>hi</p></html>") == ".html"

    def test_utf8_bom(self):
        assert detect_extension(b"\xef\xbb\xbf<!doctype html><html/>") == ".html"

    def test_bom_plus_whitespace(self):
        assert detect_extension(b"\xef\xbb\xbf \n <HTML></HTML>") == ".html"

    def test_xml_is_not_html(self):
        assert detect_extension(b'<?xml version="1.0"?><root/>') is None

    def test_div_fragment_is_not_html(self):
        assert detect_extension(b"<div>fragment</div>") is None


# =============================================================================
# _route_processor: routing order
# =============================================================================


class TestRouteProcessor:
    def test_extension_lookup_wins(self):
        # A registered extension routes directly, no sniffing involved.
        proc, key = _route_processor("doc.pdf", b"not even pdf bytes")
        assert proc is processors[".pdf"]
        assert key == ".pdf"

    def test_extensionless_pdf_sniffs_to_pdf(self):
        proc, key = _route_processor("report", b"%PDF-1.7 fake body")
        assert proc is processors[".pdf"]
        assert key == ".pdf"

    def test_unknown_extension_sniffs_content(self):
        # Unregistered extension -> magic bytes decide.
        proc, key = _route_processor("download.dat", b"%PDF-1.7 fake body")
        assert proc is processors[".pdf"]
        assert key == ".pdf"

    def test_sniffed_but_unregistered_falls_to_text(self):
        # HTML bytes with the html processor removed: the sniffed ".html"
        # has no registered processor, so the text heuristic takes over.
        # (conftest's autouse reset_processor_registry restores these.)
        del processors[".html"]
        del processors[".htm"]
        proc, key = _route_processor("page", b"<html><body>hi</body></html>")
        assert proc is processors["__text__"]
        assert key == "__text__"

    def test_sniffed_unregistered_binary_has_no_processor(self, monkeypatch):
        # Sniff resolves to an extension nobody registered; binary bytes
        # also fail the text heuristic -> no processor at all.
        monkeypatch.setattr(
            "attachments.core.detect_extension", lambda data: ".zz-unregistered"
        )
        proc, key = _route_processor("blob", bytes(range(256)))
        assert proc is None
        assert key == ""

    def test_unsniffable_binary_has_no_processor(self):
        proc, key = _route_processor("blob.bin", bytes(range(256)))
        assert proc is None
        assert key == ".bin"


# =============================================================================
# End-to-end routing through att()
# =============================================================================


class TestAttContentRouting:
    def test_extensionless_pdf_processes_as_pdf(self, tmp_path: Path):
        path = tmp_path / "report"  # no extension at all
        path.write_bytes(make_real_pdf())

        result = att(str(path), prefer="local-only")

        assert len(result) == 1
        artifact = result[0]
        assert "error" not in artifact["meta"]
        assert artifact["meta"]["kind"] == "pdf"

    def test_extensionless_xlsx_processes_as_table(self, tmp_path: Path):
        path = tmp_path / "spreadsheet"  # no extension at all
        path.write_bytes(make_real_xlsx())

        result = att(str(path), prefer="local-only")

        assert len(result) == 1
        artifact = result[0]
        assert "error" not in artifact["meta"]
        assert artifact["meta"]["kind"] == "table"
        assert "Alice" in artifact["text"]

    def test_unregistered_sniff_falls_through_to_no_processor(
        self, tmp_path: Path, monkeypatch
    ):
        # Content sniffs to an extension with no registered processor and
        # the bytes are binary: empty artifact with a note, never an error.
        monkeypatch.setattr(
            "attachments.core.detect_extension", lambda data: ".zz-unregistered"
        )
        path = tmp_path / "blob"
        path.write_bytes(bytes(range(256)))

        result = att(str(path))

        assert len(result) == 1
        artifact = result[0]
        assert "error" not in artifact["meta"]
        assert "no processor" in artifact["meta"]["note"]
        assert artifact["text"] == ""

    def test_unregistered_sniff_with_text_bytes_uses_text_processor(
        self, tmp_path: Path, monkeypatch
    ):
        # Sniff yields an unregistered extension but the bytes are text:
        # the existing text fallback still applies.
        monkeypatch.setattr(
            "attachments.core.detect_extension", lambda data: ".zz-unregistered"
        )
        path = tmp_path / "notes"
        path.write_bytes(b"plain text survives the fake sniff\n")

        result = att(str(path), prefer="local-only")

        assert len(result) == 1
        artifact = result[0]
        assert "error" not in artifact["meta"]
        assert artifact["meta"]["kind"] == "text"
        assert "plain text survives" in artifact["text"]
