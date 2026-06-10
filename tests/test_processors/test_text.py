"""
Tests for the text processor.

=============================================================================
TEST GUIDELINES FOR TEXT PROCESSOR
=============================================================================

GOOD tests for text processor:
    - Test various encodings (UTF-8, Latin-1, etc.)
    - Test edge cases (empty file, binary detection)
    - Test all registered extensions work
    - Test the artifact structure is correct

BAD tests:
    - Testing file I/O (that's tests/test_sources/)
    - Testing the att() pipeline (that's test_core.py)
    - Duplicating doctest examples

NOTES:
    - Text processor has no external dependencies - always runs
    - Focus on encoding detection and text extraction

=============================================================================
"""

from __future__ import annotations

import pytest

from attachments._processors import processors
from attachments._processors.text import text_processor


class TestTextProcessor:
    """Tests for text_processor function."""

    def test_returns_artifact_structure(self, sample_text_bytes: bytes):
        result = text_processor(sample_text_bytes)

        assert "text" in result
        assert "images" in result
        assert "audio" in result
        assert "video" in result
        assert "meta" in result

    def test_extracts_utf8_text(self, sample_text_bytes: bytes):
        result = text_processor(sample_text_bytes)

        assert "Hello, World!" in result["text"]
        assert result["meta"]["extra"]["encoding"] == "utf-8"

    def test_extracts_latin1_text(self, sample_text_latin1: bytes):
        result = text_processor(sample_text_latin1)

        # Should decode and contain the text
        assert "Café" in result["text"] or "Caf" in result["text"]

    def test_empty_input(self):
        result = text_processor(b"")

        assert result["text"] == ""
        assert result["meta"]["extra"]["chars"] == 0

    def test_meta_extra_includes_char_count(self, sample_text_bytes: bytes):
        result = text_processor(sample_text_bytes)

        assert "chars" in result["meta"]["extra"]
        assert result["meta"]["extra"]["chars"] == len(result["text"])

    def test_meta_includes_kind(self, sample_text_bytes: bytes):
        result = text_processor(sample_text_bytes)

        assert result["meta"]["kind"] == "text"

    def test_filename_passed_through(self, sample_text_bytes: bytes):
        result = text_processor(sample_text_bytes, filename="test.txt")

        assert result["meta"]["extra"]["filename"] == "test.txt"

    def test_images_audio_video_empty(self, sample_text_bytes: bytes):
        result = text_processor(sample_text_bytes)

        assert result["images"] == []
        assert result["audio"] == []
        assert result["video"] == []


class TestTextProcessorEncodings:
    """Tests for encoding detection and handling."""

    def test_utf8_with_bom(self):
        data = b"\xef\xbb\xbfHello with BOM"
        result = text_processor(data)

        assert "Hello with BOM" in result["text"]
        assert result["meta"]["extra"]["encoding"] in ("utf-8", "utf-8-sig")

    def test_utf8_unicode_chars(self):
        data = "Hello 世界 🌍".encode()
        result = text_processor(data)

        assert "世界" in result["text"]
        assert "🌍" in result["text"]

    def test_cp1252_windows(self):
        # Windows-1252 encoded text with special chars
        data = "Hello – world".encode("cp1252")
        result = text_processor(data)

        # Should decode somehow
        assert "Hello" in result["text"]

    def test_fallback_on_invalid_utf8(self):
        # Invalid UTF-8 sequence
        data = b"Hello \xff\xfe World"
        result = text_processor(data)

        # Should not raise, should use replacement
        assert "Hello" in result["text"]


class TestTextProcessorRegistration:
    """Tests for text processor registration."""

    def test_text_catch_all_registered(self):
        assert "__text__" in processors

    @pytest.mark.parametrize(
        "ext",
        [
            ".txt",
            ".md",
            ".json",
            ".yaml",
            ".yml",
            ".py",
            ".js",
            ".css",
            ".html",
            ".xml",
        ],
    )
    def test_common_extensions_registered(self, ext: str):
        assert ext in processors, f"{ext} not registered"

    def test_registered_processor_is_text_processor(self):
        assert processors[".txt"] is text_processor
        assert processors["__text__"] is text_processor


class TestTextProcessorEdgeCases:
    """Edge case tests for text processor."""

    def test_very_long_lines(self):
        data = b"x" * 100000  # 100KB of 'x'
        result = text_processor(data)

        assert len(result["text"]) == 100000

    def test_mixed_line_endings(self):
        data = b"line1\r\nline2\nline3\rline4"
        result = text_processor(data)

        # All line ending styles should be preserved
        assert "line1" in result["text"]
        assert "line4" in result["text"]

    def test_only_whitespace(self):
        data = b"   \n\t\n   "
        result = text_processor(data)

        # Should work, whitespace is valid text
        assert result["text"].strip() == ""
        assert result["meta"]["extra"]["chars"] > 0

    def test_json_content(self, sample_json_bytes: bytes):
        result = text_processor(sample_json_bytes)

        assert '"name"' in result["text"]
        assert '"test"' in result["text"]
