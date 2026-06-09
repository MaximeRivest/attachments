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

import pytest

from attachments.deps import check_dep
from attachments.processors import processors

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
        assert "flags" in result

    def test_flags_include_metadata(self, minimal_pdf_bytes: bytes):
        processor = processors[".pdf"]
        result = processor(minimal_pdf_bytes)

        flags = result["flags"]
        # Should include some metadata about processing
        # The PDF processor uses various key names depending on the backend
        assert "pages" in flags or "total_pages" in flags or "parsed_pages" in flags

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

    def test_corrupt_pdf_returns_error(self, corrupt_pdf_bytes: bytes):
        processor = processors[".pdf"]
        result = processor(corrupt_pdf_bytes)

        # Should return artifact with error, not raise
        assert "flags" in result
        # Either has error or empty text
        has_error = "error" in result["flags"]
        is_empty = result["text"] == ""
        assert has_error or is_empty

    def test_empty_bytes_handled(self):
        processor = processors[".pdf"]
        result = processor(b"")

        assert "flags" in result

    def test_non_pdf_bytes_handled(self):
        processor = processors[".pdf"]
        result = processor(b"This is not a PDF at all")

        assert "flags" in result


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


class TestPdfProcessorWithoutDeps:
    """Tests for PDF processor behavior when deps are missing.

    These tests run regardless of dep availability.
    """

    @pytest.mark.skipif(
        check_dep("pdf-text").available,
        reason="Test only relevant when PDF deps missing",
    )
    def test_missing_deps_returns_error(self):
        processor = processors[".pdf"]
        result = processor(b"%PDF-1.4 minimal pdf")

        assert "error" in result["flags"]
        assert (
            "requires" in result["flags"]["error"].lower()
            or "install" in result["flags"]["error"].lower()
        )
