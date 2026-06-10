"""
Tests for the PDF processor.

=============================================================================
TEST GUIDELINES FOR PDF PROCESSOR
=============================================================================

GOOD tests for PDF processor:
    - Use pytest.mark.skipif for optional deps
    - Test with real PDF bytes (fixture from conftest.py)
    - Test page range options
    - Test error handling for corrupt PDFs
    - Test fallback behavior when deps missing

BAD tests:
    - Assuming pypdf/pymupdf are always installed
    - Testing internal implementation details
    - Creating PDFs manually in each test (use fixtures)

NOTES:
    - PDF processor requires pypdf or PyPDF2 for text extraction
    - pymupdf is optional for image rendering
    - Tests skip gracefully if deps not installed

=============================================================================
"""

from __future__ import annotations

import io

import pytest

from attachments._processors import processors
from attachments.deps import check_dep
from attachments.types import ERROR_PASSWORD_REQUIRED

# Skip all tests in this module if PDF deps not available
pytestmark = pytest.mark.skipif(
    not check_dep("pdf-text").available,
    reason="PDF text extraction deps (pypdf/PyPDF2) not installed",
)


class TestPdfProcessor:
    """Tests for PDF processor with real PDF files."""

    def test_processor_registered(self):
        assert ".pdf" in processors

    def test_returns_artifact_structure(self, minimal_pdf_bytes: bytes):
        processor = processors[".pdf"]
        result = processor(minimal_pdf_bytes)

        assert "text" in result
        assert "images" in result
        assert "audio" in result
        assert "video" in result
        assert "meta" in result

    def test_meta_includes_kind_and_extra(self, minimal_pdf_bytes: bytes):
        processor = processors[".pdf"]
        result = processor(minimal_pdf_bytes)

        assert result["meta"]["kind"] == "pdf"
        extra = result["meta"]["extra"]
        # Should include some metadata about processing
        # The PDF processor uses various key names depending on the backend
        assert "pages" in extra or "total_pages" in extra or "parsed_pages" in extra

    def test_images_audio_video_are_lists(self, minimal_pdf_bytes: bytes):
        processor = processors[".pdf"]
        result = processor(minimal_pdf_bytes)

        assert isinstance(result["images"], list)
        assert isinstance(result["audio"], list)
        assert isinstance(result["video"], list)


class TestPdfProcessorOptions:
    """Tests for PDF processor options."""

    def test_page_range_start(self, minimal_pdf_bytes: bytes):
        processor = processors[".pdf"]
        # Process starting from page 1 (0-indexed)
        result = processor(minimal_pdf_bytes, page_start=0)

        # Should not error
        assert "text" in result

    def test_page_end_option(self, minimal_pdf_bytes: bytes):
        processor = processors[".pdf"]
        result = processor(minimal_pdf_bytes, page_end=1)

        assert "text" in result

    def test_max_pages_option(self, minimal_pdf_bytes: bytes):
        processor = processors[".pdf"]
        result = processor(minimal_pdf_bytes, max_pages=1)

        assert "text" in result


class TestPdfProcessorErrors:
    """Tests for PDF processor error handling."""

    def test_corrupt_pdf_returns_parse_error(self, corrupt_pdf_bytes: bytes):
        from attachments.types import ERROR_PARSE

        processor = processors[".pdf"]
        result = processor(corrupt_pdf_bytes)

        # Should return a typed parse error artifact, not raise and not
        # masquerade as a successful empty extraction.
        assert result["text"] == ""
        assert result["meta"]["error"]["code"] == ERROR_PARSE

    def test_empty_bytes_returns_parse_error(self):
        from attachments.types import ERROR_PARSE

        processor = processors[".pdf"]
        result = processor(b"")

        assert result["meta"]["error"]["code"] == ERROR_PARSE

    def test_non_pdf_bytes_returns_parse_error(self):
        from attachments.types import ERROR_PARSE

        processor = processors[".pdf"]
        result = processor(b"This is not a PDF at all")

        assert result["meta"]["error"]["code"] == ERROR_PARSE


@pytest.mark.skipif(
    not check_dep("pdf-images").available,
    reason="PDF image rendering deps (pymupdf) not installed",
)
class TestPdfImageRendering:
    """Tests for PDF image rendering (requires pymupdf)."""

    def test_render_images_option(self, sample_pdf_bytes: bytes):
        processor = processors[".pdf"]
        result = processor(sample_pdf_bytes, render_images=True)

        # Should return without error
        assert "images" in result

    def test_images_dpi_option(self, sample_pdf_bytes: bytes):
        processor = processors[".pdf"]
        result = processor(sample_pdf_bytes, render_images=True, images_dpi=72)

        assert "images" in result


class TestPdfPassword:
    """Encrypted PDFs return a typed password-required error."""

    @pytest.fixture
    def encrypted_pdf_bytes(self) -> bytes:
        pytest.importorskip("pypdf")
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.encrypt("secret")
        buf = io.BytesIO()
        writer.write(buf)
        return buf.getvalue()

    def test_missing_password_returns_password_required(self, encrypted_pdf_bytes):
        result = processors[".pdf"](encrypted_pdf_bytes)

        assert result["meta"]["error"]["code"] == ERROR_PASSWORD_REQUIRED
        assert "password" in result["meta"]["error"]["message"].lower()

    def test_wrong_password_returns_password_required(self, encrypted_pdf_bytes):
        result = processors[".pdf"](encrypted_pdf_bytes, password="nope")

        assert result["meta"]["error"]["code"] == ERROR_PASSWORD_REQUIRED

    def test_correct_password_succeeds(self, encrypted_pdf_bytes):
        result = processors[".pdf"](
            encrypted_pdf_bytes, password="secret", render_images=False
        )

        assert "error" not in result["meta"]
        assert result["meta"]["kind"] == "pdf"


# Missing-dependency behavior is covered by the always-runnable tests in
# tests/test_processors/test_missing_deps.py (this module is skipped
# entirely when PDF deps are absent, so such tests could never run here).


@pytest.mark.skipif(
    not check_dep("pdf-images").available,
    reason="PyMuPDF needed to build a text PDF fixture",
)
class TestPdfSegments:
    """meta.segments carries page boundaries (IR contract: pdf pages)."""

    @pytest.fixture
    def two_page_text_pdf(self) -> bytes:
        pymupdf = pytest.importorskip("pymupdf")

        doc = pymupdf.open()
        for label in ("alpha page", "beta page"):
            page = doc.new_page()
            page.insert_text((72, 72), label)
        data = doc.tobytes()
        doc.close()
        return data

    def test_page_segments_cover_text(self, two_page_text_pdf: bytes):
        result = processors[".pdf"](two_page_text_pdf, render_images=False)

        assert "error" not in result["meta"]
        segments = result["meta"]["segments"]
        assert [s["kind"] for s in segments] == ["page", "page"]
        assert [s["label"] for s in segments] == ["page 1", "page 2"]

        text = result["text"]
        assert text[segments[0]["start"] : segments[0]["end"]] == "alpha page"
        assert text[segments[1]["start"] : segments[1]["end"]] == "beta page"
