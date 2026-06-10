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
import sys

import pytest

from attachments._processors import processors
from attachments._processors.pdf import SCANNED_PDF_HINT
from attachments.deps import check_dep, clear_cache
from attachments.types import (
    ERROR_INVALID_OPTION,
    ERROR_MISSING_DEPENDENCY,
    ERROR_PASSWORD_REQUIRED,
    ERROR_PROCESSING,
    is_missing_dependency,
)

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

    def test_corrupt_pdf_does_not_spew_pypdf_log_noise(
        self, corrupt_pdf_bytes: bytes, caplog
    ):
        """pypdf's 'EOF marker not found' must not reach the console.

        Problems are reported in-band (error artifacts), so third-party
        log spew is suppressed during parsing — and the logger levels are
        restored afterwards.
        """
        import logging

        level_before = logging.getLogger("pypdf").level
        processor = processors[".pdf"]
        with caplog.at_level(logging.DEBUG):
            result = processor(corrupt_pdf_bytes)

        assert result["meta"]["error"]["code"]  # still the typed artifact
        assert not [r for r in caplog.records if r.name.startswith(("pypdf", "PyPDF2"))]
        assert logging.getLogger("pypdf").level == level_before


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


@pytest.mark.skipif(
    not check_dep("pdf-images").available,
    reason="PyMuPDF needed to build/render the scanned PDF fixture",
)
class TestPdfOcr:
    """ocr option: "auto" (default) | True | False — text layer always wins."""

    @pytest.fixture
    def mask_ocr(self, monkeypatch):
        """Simulate rapidocr_onnxruntime being uninstalled."""
        monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", None)
        clear_cache()
        yield
        clear_cache()

    @pytest.fixture
    def scanned_pdf_bytes(self) -> bytes:
        """An image-only PDF (no text layer): text rendered via PIL, embedded.

        Large clear black-on-white text so CPU OCR is reliable.
        """
        pymupdf = pytest.importorskip("pymupdf")
        PIL_Image = pytest.importorskip("PIL.Image")
        from PIL import ImageDraw, ImageFont

        img = PIL_Image.new("RGB", (1200, 400), "white")
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.load_default(size=120)
        except TypeError:  # older Pillow: load_default() takes no size kwarg
            font = ImageFont.load_default()
        draw.text((40, 120), "HELLO WORLD 42", fill="black", font=font)
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        doc = pymupdf.open()
        page = doc.new_page(width=600, height=200)
        page.insert_image(pymupdf.Rect(0, 0, 600, 200), stream=buf.getvalue())
        data = doc.tobytes()
        doc.close()
        return data

    def test_scanned_pdf_has_no_text_layer(self, scanned_pdf_bytes: bytes):
        result = processors[".pdf"](scanned_pdf_bytes, ocr=False)

        assert "error" not in result["meta"]
        assert result["text"].strip() == ""

    def test_ocr_false_never_runs(self, scanned_pdf_bytes: bytes):
        result = processors[".pdf"](scanned_pdf_bytes, ocr=False)

        extra = result["meta"]["extra"]
        assert "ocr" not in extra
        assert "ocr_hint" not in extra

    @pytest.mark.skipif(
        not check_dep("ocr").available, reason="rapidocr_onnxruntime not installed"
    )
    def test_auto_ocr_recovers_text_from_scanned_pdf(self, scanned_pdf_bytes: bytes):
        # Real CPU inference; the first call also loads the model (slow,
        # but the engine is cached at module level for the whole session).
        result = processors[".pdf"](scanned_pdf_bytes)  # ocr defaults to "auto"

        assert "error" not in result["meta"]
        assert "HELLO WORLD 42" in result["text"]
        extra = result["meta"]["extra"]
        assert extra["ocr"] is True
        assert extra["ocr_backend"] == "rapidocr"
        # Segments are built over the OCR text, like the text path.
        segments = result["meta"]["segments"]
        assert segments[0]["kind"] == "page"
        assert segments[0]["label"] == "page 1"
        text = result["text"]
        assert "HELLO WORLD 42" in text[segments[0]["start"] : segments[0]["end"]]

    @pytest.mark.skipif(
        not check_dep("ocr").available, reason="rapidocr_onnxruntime not installed"
    )
    def test_forced_ocr_renders_pages_when_images_disabled(
        self, scanned_pdf_bytes: bytes
    ):
        result = processors[".pdf"](scanned_pdf_bytes, ocr=True, render_images=False)

        assert "error" not in result["meta"]
        assert "HELLO WORLD 42" in result["text"]
        assert result["images"] == []  # OCR-only renders are not emitted

    @pytest.mark.skipif(
        not check_dep("ocr").available, reason="rapidocr_onnxruntime not installed"
    )
    def test_text_layer_wins_over_ocr(self):
        pymupdf = pytest.importorskip("pymupdf")
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "real text layer")
        data = doc.tobytes()
        doc.close()

        result = processors[".pdf"](data, ocr=True, render_images=False)

        assert result["text"] == "real text layer"
        assert "ocr" not in result["meta"]["extra"]

    def test_auto_missing_dep_adds_hint_and_note(
        self, scanned_pdf_bytes: bytes, mask_ocr
    ):
        result = processors[".pdf"](scanned_pdf_bytes)

        assert "error" not in result["meta"]  # never an error under auto
        assert result["text"].strip() == ""  # still empty, but not silently
        extra = result["meta"]["extra"]
        assert extra["ocr_hint"] == SCANNED_PDF_HINT
        # note and extra.ocr_hint stay consistent; local remedy first,
        # free hosted tier second; short enough that the repr never clips.
        assert result["meta"]["note"] == SCANNED_PDF_HINT
        assert "pip install attachments[ocr]" in result["meta"]["note"]
        assert "attachments.dev" in result["meta"]["note"]
        assert len(result["meta"]["note"]) < 150

    def test_auto_missing_dep_note_surfaces_in_repr(
        self, scanned_pdf_bytes: bytes, mask_ocr
    ):
        """End to end: a first-run user who just prints the result sees the
        OCR remedy AND the free hosted tier, unclipped."""
        from attachments import Artifacts
        from attachments.types import normalize_artifact

        result = processors[".pdf"](scanned_pdf_bytes)
        arts = Artifacts([normalize_artifact(result, "scan.pdf")])

        rendered = repr(arts)
        assert "pip install attachments[ocr]" in rendered
        assert "attachments.dev" in rendered
        assert "…" not in rendered.split("\n")[1]  # remedy never clipped

    def test_forced_ocr_missing_dep_returns_typed_error(
        self, scanned_pdf_bytes: bytes, mask_ocr
    ):
        result = processors[".pdf"](scanned_pdf_bytes, ocr=True)

        assert is_missing_dependency(result)
        error = result["meta"]["error"]
        assert error["code"] == ERROR_MISSING_DEPENDENCY
        assert "pip install attachments[ocr]" in error["message"]


@pytest.mark.skipif(
    not check_dep("pdf-images").available,
    reason="PyMuPDF needed to build/render the scanned PDF fixture",
)
class TestPdfOcrLighton:
    """ocr_engine=lighton: pages are OCRed via a remote vLLM endpoint."""

    @pytest.fixture
    def scanned_pdf_bytes(self) -> bytes:
        """Minimal image-only PDF (no text layer)."""
        pymupdf = pytest.importorskip("pymupdf")
        PIL_Image = pytest.importorskip("PIL.Image")

        img = PIL_Image.new("RGB", (300, 100), "white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        doc = pymupdf.open()
        page = doc.new_page(width=300, height=100)
        page.insert_image(pymupdf.Rect(0, 0, 300, 100), stream=buf.getvalue())
        data = doc.tobytes()
        doc.close()
        return data

    @pytest.fixture
    def lighton_env(self, monkeypatch):
        monkeypatch.setenv("ATTACHMENTS_LIGHTON_URL", "http://127.0.0.1:8100/v1")
        monkeypatch.delenv("ATTACHMENTS_LIGHTON_MODEL", raising=False)

    @pytest.fixture
    def fake_post(self, monkeypatch):
        httpx = pytest.importorskip("httpx")
        holder: dict = {"calls": [], "fail": False}

        class _Resp:
            def raise_for_status(self):
                if holder["fail"]:
                    raise RuntimeError("HTTP 500 from endpoint")

            def json(self):
                return {"choices": [{"message": {"content": "PAGE VIA LIGHTON"}}]}

        def _post(url, json=None, timeout=None):
            holder["calls"].append({"url": url, "json": json})
            return _Resp()

        monkeypatch.setattr(httpx, "post", _post)
        return holder

    def test_lighton_ocr_text_and_request_shape(
        self, scanned_pdf_bytes: bytes, lighton_env, fake_post
    ):
        result = processors[".pdf"](
            scanned_pdf_bytes, ocr=True, ocr_engine="lighton", render_images=False
        )

        assert "error" not in result["meta"]
        assert result["text"] == "PAGE VIA LIGHTON"
        extra = result["meta"]["extra"]
        assert extra["ocr"] is True
        assert extra["ocr_backend"] == "lighton"

        call = fake_post["calls"][0]  # one chat completion per page
        assert call["url"] == "http://127.0.0.1:8100/v1/chat/completions"
        payload = call["json"]
        assert payload["model"] == "lightonai/LightOnOCR-2-1B"
        content = payload["messages"][0]["content"]
        assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")

    def test_explicit_lighton_without_url_is_invalid_option(
        self, scanned_pdf_bytes: bytes, monkeypatch
    ):
        monkeypatch.delenv("ATTACHMENTS_LIGHTON_URL", raising=False)

        result = processors[".pdf"](scanned_pdf_bytes, ocr=True, ocr_engine="lighton")

        error = result["meta"]["error"]
        assert error["code"] == ERROR_INVALID_OPTION
        assert "ATTACHMENTS_LIGHTON_URL" in error["message"]
        assert "SERVER capability" in error["message"]
        assert result["meta"]["kind"] == "pdf"

    def test_auto_ocr_lighton_without_url_falls_back(
        self, scanned_pdf_bytes: bytes, monkeypatch
    ):
        monkeypatch.delenv("ATTACHMENTS_LIGHTON_URL", raising=False)
        monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", None)
        clear_cache()
        try:
            result = processors[".pdf"](
                scanned_pdf_bytes, ocr="auto", ocr_engine="lighton"
            )
        finally:
            clear_cache()

        assert "error" not in result["meta"]
        extra = result["meta"]["extra"]
        assert extra["ocr_engine_fallback"] == "rapidocr"
        assert extra["ocr_hint"] == SCANNED_PDF_HINT

    def test_endpoint_failure_is_processing_error(
        self, scanned_pdf_bytes: bytes, lighton_env, fake_post
    ):
        fake_post["fail"] = True

        result = processors[".pdf"](scanned_pdf_bytes, ocr=True, ocr_engine="lighton")

        error = result["meta"]["error"]
        assert error["code"] == ERROR_PROCESSING
        assert "LightOn OCR request failed" in error["message"]
        assert "running and reachable" in error["message"]

    def test_unknown_engine_is_invalid_option(self, scanned_pdf_bytes: bytes):
        result = processors[".pdf"](scanned_pdf_bytes, ocr=True, ocr_engine="bogus")

        error = result["meta"]["error"]
        assert error["code"] == ERROR_INVALID_OPTION
        assert "bogus" in error["message"]
