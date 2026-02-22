"""
Integration tests for the core att() function.

=============================================================================
TEST GUIDELINES FOR CORE
=============================================================================

GOOD tests for core:
    - Test the full pipeline: input -> unpack -> process -> output
    - Test DSL option parsing integration
    - Test option precedence (explicit > DSL > defaults)
    - Test error artifact structure
    - Test multiple files in a directory
    - Use real files via fixtures (not mocks for integration tests)

BAD tests:
    - Testing unpack in isolation (that's test_unpack.py)
    - Testing processors in isolation (that's test_processors/)
    - Testing DSL parsing in isolation (that's test_dsl.py)
    - Mocking everything (defeats purpose of integration tests)

NOTES:
    - att() is the main entry point, so integration tests are critical
    - Use tmp_path for file fixtures
    - These tests may be slower than unit tests - that's OK

=============================================================================
"""

from __future__ import annotations

from pathlib import Path

import pytest

from attachments import att, configure
from attachments.core import (
    _apply_source_options,
    _empty_artifact,
    _error_artifact,
    _has_meaningful_error,
    _is_empty_result,
    _normalize_artifact,
)


class TestErrorArtifact:
    """Tests for _error_artifact helper."""

    def test_structure(self):
        result = _error_artifact("test.pdf", "file not found")

        assert result["text"] == ""
        assert result["images"] == []
        assert result["audio"] == []
        assert result["video"] == []
        assert result["flags"]["source"] == "test.pdf"
        assert result["flags"]["error"] == "file not found"


class TestEmptyArtifact:
    """Tests for _empty_artifact helper."""

    def test_structure(self):
        result = _empty_artifact("test.bin", "no processor")

        assert result["text"] == ""
        assert result["flags"]["note"] == "no processor"


class TestHasMeaningfulError:
    """Tests for _has_meaningful_error - detects dep-related errors."""

    def test_detects_requires(self):
        artifact = {"flags": {"error": "This feature requires pypdf"}}
        assert _has_meaningful_error(artifact) is True

    def test_detects_not_installed(self):
        artifact = {"flags": {"error": "Module not installed"}}
        assert _has_meaningful_error(artifact) is True

    def test_detects_import_error(self):
        artifact = {"flags": {"error": "ImportError: No module named 'foo'"}}
        assert _has_meaningful_error(artifact) is True

    def test_ignores_other_errors(self):
        artifact = {"flags": {"error": "File not found"}}
        assert _has_meaningful_error(artifact) is False

    def test_no_error_returns_false(self):
        artifact = {"flags": {}}
        assert _has_meaningful_error(artifact) is False


class TestIsEmptyResult:
    """Tests for _is_empty_result - checks for meaningful content."""

    def test_empty_text_no_media(self):
        artifact = {"text": "", "images": [], "audio": [], "video": []}
        assert _is_empty_result(artifact) is True

    def test_whitespace_only_is_empty(self):
        artifact = {"text": "   \n\t  ", "images": [], "audio": [], "video": []}
        assert _is_empty_result(artifact) is True

    def test_has_text_not_empty(self):
        artifact = {"text": "content", "images": [], "audio": [], "video": []}
        assert _is_empty_result(artifact) is False

    def test_has_images_not_empty(self):
        artifact = {"text": "", "images": [{"data": "..."}], "audio": [], "video": []}
        assert _is_empty_result(artifact) is False


class TestNormalizeArtifact:
    """Tests for _normalize_artifact - ensures consistent structure."""

    def test_adds_missing_keys(self):
        artifact = {"text": "hello"}
        result = _normalize_artifact(artifact, "test.txt")

        assert result["images"] == []
        assert result["audio"] == []
        assert result["video"] == []
        assert result["flags"]["source"] == "test.txt"

    def test_preserves_existing_values(self):
        artifact = {"text": "hello", "images": [{"data": "img"}], "flags": {"custom": True}}
        result = _normalize_artifact(artifact, "test.txt")

        assert result["text"] == "hello"
        assert len(result["images"]) == 1
        assert result["flags"]["custom"] is True
        assert result["flags"]["source"] == "test.txt"


class TestApplySourceOptions:
    """Tests for _apply_source_options - handles source-specific options."""

    def test_github_ref_added(self):
        opts = {"ref": "main", "other": "value"}
        result = _apply_source_options("github://owner/repo", opts)

        assert result == "github://owner/repo?ref=main"
        assert "ref" not in opts  # Consumed
        assert opts["other"] == "value"  # Preserved

    def test_non_github_unchanged(self):
        opts = {"ref": "ignored"}
        result = _apply_source_options("/local/path.txt", opts)

        assert result == "/local/path.txt"
        # ref is NOT consumed for non-github
        assert "ref" in opts


class TestAttTextFile:
    """Integration tests for att() with text files."""

    def test_single_text_file(self, tmp_path: Path, sample_text_bytes: bytes):
        file_path = tmp_path / "hello.txt"
        file_path.write_bytes(sample_text_bytes)

        result = att(str(file_path))

        assert len(result) == 1
        assert "Hello" in result[0]["text"]
        assert result[0]["flags"]["source"] == "hello.txt"

    def test_text_file_with_dsl_ignored(self, tmp_path: Path, sample_text_bytes: bytes):
        """DSL options for text files don't affect processing (no page ranges, etc.)."""
        file_path = tmp_path / "hello.txt"
        file_path.write_bytes(sample_text_bytes)

        # DSL options are parsed but text processor doesn't use them
        result = att(f"{file_path}[pages: 1-4]")

        assert len(result) == 1
        assert "Hello" in result[0]["text"]


class TestAttDirectory:
    """Integration tests for att() with directories."""

    def test_directory_multiple_files(self, sample_directory: Path):
        result = att(str(sample_directory))

        # Should have multiple artifacts
        assert len(result) >= 2

        # Check we got expected files
        sources = {a["flags"]["source"] for a in result}
        assert "readme.txt" in sources
        assert "data.json" in sources

    def test_directory_with_subdirs(self, sample_directory: Path):
        result = att(str(sample_directory))

        # Should include files from subdirectories
        sources = [a["flags"]["source"] for a in result]
        assert any("nested.md" in s or "subdir" in s for s in sources)


class TestAttZip:
    """Integration tests for att() with ZIP archives."""

    def test_zip_file_expanded(self, tmp_path: Path, sample_zip_bytes: bytes):
        zip_path = tmp_path / "archive.zip"
        zip_path.write_bytes(sample_zip_bytes)

        result = att(str(zip_path))

        assert len(result) == 1
        assert "Hello" in result[0]["text"]


class TestAttDslIntegration:
    """Integration tests for DSL options in att()."""

    def test_explicit_options_override_dsl(self, tmp_path: Path, sample_text_bytes: bytes):
        file_path = tmp_path / "test.txt"
        file_path.write_bytes(sample_text_bytes)

        # DSL says sheet: Sales, explicit says sheet: Revenue
        # (These don't affect text, but test the merging)
        result = att(f"{file_path}[sheet: Sales]", sheet="Revenue")

        # Just verify it doesn't crash
        assert len(result) == 1


class TestAttErrors:
    """Tests for error handling in att()."""

    def test_nonexistent_path_returns_error(self):
        result = att("/nonexistent/path/file.pdf")

        assert len(result) == 1
        assert "error" in result[0]["flags"]
        assert "unpack failed" in result[0]["flags"]["error"]

    def test_error_artifact_has_correct_structure(self):
        result = att("/nonexistent/path/file.pdf")

        artifact = result[0]
        assert artifact["text"] == ""
        assert artifact["images"] == []
        assert artifact["audio"] == []
        assert artifact["video"] == []
        assert "flags" in artifact


class TestAttPreferModes:
    """Tests for prefer option in att()."""

    def test_prefer_local_default(self, tmp_path: Path, sample_text_bytes: bytes):
        file_path = tmp_path / "test.txt"
        file_path.write_bytes(sample_text_bytes)

        result = att(str(file_path), prefer="local")

        assert len(result) == 1
        assert "Hello" in result[0]["text"]

    def test_prefer_local_only(self, tmp_path: Path, sample_text_bytes: bytes):
        file_path = tmp_path / "test.txt"
        file_path.write_bytes(sample_text_bytes)

        result = att(str(file_path), prefer="local-only")

        assert len(result) == 1
        assert "Hello" in result[0]["text"]

    def test_prefer_service_only_without_key_errors(self, tmp_path: Path, sample_text_bytes: bytes):
        file_path = tmp_path / "test.txt"
        file_path.write_bytes(sample_text_bytes)

        result = att(str(file_path), prefer="service-only")

        assert len(result) == 1
        # Should error because no API key
        assert "error" in result[0]["flags"]
        assert "API key" in result[0]["flags"]["error"] or "api_key" in result[0]["flags"]["error"].lower()


class TestAttWithBinaryFiles:
    """Tests for att() with binary/non-text files."""

    def test_binary_file_no_processor(self, tmp_path: Path, sample_binary_bytes: bytes):
        file_path = tmp_path / "binary.bin"
        file_path.write_bytes(sample_binary_bytes)

        result = att(str(file_path))

        assert len(result) == 1
        # Either has a note about no processor or empty text
        flags = result[0]["flags"]
        has_note = "note" in flags
        has_error = "error" in flags
        is_empty = result[0]["text"] == ""
        assert has_note or has_error or is_empty


class TestAttArtifactValidator:
    """Tests using the assert_artifact fixture."""

    def test_text_file_valid_artifact(
        self, tmp_path: Path, sample_text_bytes: bytes, assert_artifact
    ):
        file_path = tmp_path / "test.txt"
        file_path.write_bytes(sample_text_bytes)

        result = att(str(file_path))

        assert_artifact(result[0], has_text=True)

    def test_nonexistent_file_error_artifact(self, assert_artifact):
        result = att("/nonexistent/file.txt")

        assert_artifact(result[0], has_error=True)
