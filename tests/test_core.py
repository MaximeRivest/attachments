"""
Integration tests for the core att() function.

=============================================================================
TEST GUIDELINES FOR CORE
=============================================================================

GOOD tests for core:
    - Test the full pipeline: input -> unpack -> process -> output
    - Test DSL option parsing integration
    - Test option precedence (explicit > DSL > defaults)
    - Test error artifact structure (typed meta.error codes)
    - Test routing decisions (typed missing-dependency fallback)
    - Use real files via fixtures (not mocks for integration tests)

BAD tests:
    - Testing unpack in isolation (that's tests/test_sources/)
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

from attachments import att, register_processor
from attachments.core import (
    _apply_source_options,
    _artifact_from_exception,
    _empty_artifact,
    _process_single,
)
from attachments.types import (
    ERROR_MISSING_DEPENDENCY,
    ERROR_PARSE,
    ERROR_PROCESSING,
    ERROR_SERVICE,
    ERROR_UNPACK,
    error_artifact,
    make_artifact,
    missing_dep_artifact,
)


class TestEmptyArtifact:
    """Tests for _empty_artifact helper."""

    def test_structure(self):
        result = _empty_artifact("test.bin", "no processor")

        assert result["text"] == ""
        assert result["meta"]["note"] == "no processor"
        assert "error" not in result["meta"]


class TestArtifactFromException:
    """Tests for converting processor exceptions to typed errors."""

    def test_import_error_is_missing_dependency(self):
        result = _artifact_from_exception("f.pdf", ImportError("no pypdf"), "local")
        assert result["meta"]["error"]["code"] == ERROR_MISSING_DEPENDENCY

    def test_other_exception_is_processing_error(self):
        result = _artifact_from_exception("f.pdf", ValueError("boom"), "local")
        assert result["meta"]["error"]["code"] == ERROR_PROCESSING
        assert "boom" in result["meta"]["error"]["message"]


class TestTypedFallbackRouting:
    """The local->service fallback decision is typed (is_missing_dependency)."""

    def test_missing_dep_artifact_triggers_service_fallback(self, monkeypatch):
        @register_processor(".miss")
        def _local_missing(data: bytes, **_opts):
            return missing_dep_artifact("a.miss", "pdf")

        # Patch the deep target so the real via-tagging in
        # core._process_via_service is exercised (not pre-set by the fake).
        def _service_ok(data, *, filename=None, api_key=None, **_opts):
            return make_artifact(text="from service")

        monkeypatch.setattr("attachments.service.process_via_service", _service_ok)

        out = _process_single("a.miss", b"x", prefer="local", api_key="k")
        assert out["text"] == "from service"
        assert out["meta"]["via"] == "service"

    def test_missing_dep_without_key_returns_local_result(self, monkeypatch):
        @register_processor(".miss")
        def _local_missing(data: bytes, **_opts):
            return missing_dep_artifact("a.miss", "pdf")

        def _boom(*_args, **_kwargs):
            raise AssertionError("service must not be called without a key")

        monkeypatch.setattr("attachments.core._process_via_service", _boom)

        out = _process_single("a.miss", b"x", prefer="local", api_key=None)
        assert out["meta"]["error"]["code"] == ERROR_MISSING_DEPENDENCY

    def test_parse_error_does_not_trigger_fallback(self, monkeypatch):
        """A parse-error result (no exception raised) is final in local mode."""
        called = {"service": False}

        @register_processor(".bad")
        def _local_parse_error(data: bytes, **_opts):
            return error_artifact("a.bad", ERROR_PARSE, "corrupt file")

        def _service_ok(filename, data, key, **_opts):
            called["service"] = True
            return make_artifact(text="from service")

        monkeypatch.setattr("attachments.core._process_via_service", _service_ok)

        out = _process_single("a.bad", b"x", prefer="local", api_key="k")
        assert called["service"] is False
        assert out["meta"]["error"]["code"] == ERROR_PARSE

    def test_local_success_does_not_call_service(self, monkeypatch):
        called = {"service": False}

        @register_processor(".foo")
        def _local_ok(data: bytes, **_opts):
            return make_artifact(text="local")

        def _service(*_args, **_kwargs):
            called["service"] = True
            return make_artifact(text="service")

        monkeypatch.setattr("attachments.core._process_via_service", _service)

        out = _process_single("a.foo", b"x", prefer="local", api_key="k")
        assert out["text"] == "local"
        assert called["service"] is False

    def test_att_missing_dep_falls_back_to_service_end_to_end(
        self, tmp_path: Path, monkeypatch
    ):
        """The full att() pipeline routes a typed missing-dep result to the
        service and tags/normalizes the result (via, source)."""

        @register_processor(".miss")
        def _local_missing(data: bytes, **_opts):
            return missing_dep_artifact("a.miss", "pdf")

        def _service_ok(data, *, filename=None, api_key=None, **_opts):
            return make_artifact(text="from service")

        monkeypatch.setattr("attachments.service.process_via_service", _service_ok)

        file_path = tmp_path / "a.miss"
        file_path.write_bytes(b"x")

        out = att(str(file_path), api_key="k")

        assert len(out) == 1
        assert out[0]["text"] == "from service"
        assert out[0]["meta"]["via"] == "service"
        assert out[0]["meta"]["source"] == "a.miss"

    def test_att_parse_error_with_key_does_not_call_service(
        self, tmp_path: Path, monkeypatch
    ):
        """Even with an API key, a parse-error result is final through att()."""
        called = {"service": False}

        @register_processor(".bad")
        def _local_parse_error(data: bytes, **_opts):
            return error_artifact("a.bad", ERROR_PARSE, "corrupt file")

        def _service(data, *, filename=None, api_key=None, **_opts):
            called["service"] = True
            return make_artifact(text="from service")

        monkeypatch.setattr("attachments.service.process_via_service", _service)

        file_path = tmp_path / "a.bad"
        file_path.write_bytes(b"x")

        out = att(str(file_path), api_key="k")

        assert called["service"] is False
        assert out[0]["meta"]["error"]["code"] == ERROR_PARSE


class TestApplySourceOptions:
    """Tests for _apply_source_options - handles source-specific options."""

    def test_github_ref_added(self):
        opts = {"ref": "main", "other": "value"}
        result = _apply_source_options("github://owner/repo", opts)

        assert result == "github://owner/repo?ref=main"
        assert "ref" not in opts  # Consumed
        assert opts["other"] == "value"  # Preserved

    def test_github_branch_and_tag_aliases(self):
        """Schema aliases (branch/tag) resolve to ref and are consumed."""
        opts = {"branch": "dev"}
        assert (
            _apply_source_options("github://owner/repo", opts)
            == "github://owner/repo?ref=dev"
        )
        assert opts == {}

        opts = {"tag": "v1.0.0"}
        assert (
            _apply_source_options("https://github.com/owner/repo", opts)
            == "https://github.com/owner/repo?ref=v1.0.0"
        )
        assert opts == {}

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
        assert result[0]["meta"]["source"] == "hello.txt"

    def test_happy_path_meta_optional_keys_absent(
        self, tmp_path: Path, sample_text_bytes: bytes
    ):
        """Optional meta keys are ABSENT on success, never None (IR contract)."""
        file_path = tmp_path / "hello.txt"
        file_path.write_bytes(sample_text_bytes)

        meta = att(str(file_path))[0]["meta"]

        assert set(meta) == {"source", "kind", "extra"}
        for key in ("via", "error", "note", "warnings", "segments"):
            assert key not in meta
        assert all(v is not None for v in meta.values())
        assert all(v is not None for v in meta["extra"].values())

    def test_text_file_with_dsl_warns_unknown_option(
        self, tmp_path: Path, sample_text_bytes: bytes
    ):
        """The text processor declares no options, so any DSL option is
        dropped with an unknown-option warning (never silently)."""
        file_path = tmp_path / "hello.txt"
        file_path.write_bytes(sample_text_bytes)

        result = att(f"{file_path}[pages: 1-4]")

        assert len(result) == 1
        assert "Hello" in result[0]["text"]
        assert result[0]["meta"]["warnings"] == ["Unknown option 'pages' for .txt"]

    @pytest.mark.parametrize("key", ["filename", "data", "api_key", "prefer"])
    def test_internal_parameter_names_as_options_never_raise(
        self, tmp_path: Path, sample_text_bytes: bytes, key: str
    ):
        """Option keys that collide with internal parameter names must be
        dropped with an unknown-option warning — never a TypeError out of
        att() (options travel as a plain dict, not **kwargs)."""
        file_path = tmp_path / "hello.txt"
        file_path.write_bytes(sample_text_bytes)

        result = att(f"{file_path}[{key}: x]")

        assert len(result) == 1
        assert "Hello" in result[0]["text"]
        assert "error" not in result[0]["meta"]
        assert result[0]["meta"]["warnings"] == [f"Unknown option '{key}' for .txt"]


class TestAttDirectory:
    """Integration tests for att() with directories."""

    def test_directory_multiple_files(self, sample_directory: Path):
        result = att(str(sample_directory))

        # Should have multiple artifacts
        assert len(result) >= 2

        # Check we got expected files
        sources = {a["meta"]["source"] for a in result}
        assert "readme.txt" in sources
        assert "data.json" in sources

    def test_directory_with_subdirs(self, sample_directory: Path):
        result = att(str(sample_directory))

        # Should include files from subdirectories
        sources = [a["meta"]["source"] for a in result]
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

    def test_explicit_options_override_dsl(
        self, tmp_path: Path, sample_text_bytes: bytes
    ):
        file_path = tmp_path / "test.txt"
        file_path.write_bytes(sample_text_bytes)

        # DSL says sheet: Sales, explicit says sheet: Revenue
        # (These don't affect text, but test the merging)
        result = att(f"{file_path}[sheet: Sales]", sheet="Revenue")

        # Just verify it doesn't crash
        assert len(result) == 1


class TestOptionResolutionEndToEnd:
    """Options resolve per file against the matched processor's schema."""

    @pytest.fixture
    def two_page_pdf_path(self, tmp_path: Path) -> Path:
        pymupdf = pytest.importorskip("pymupdf")

        doc = pymupdf.open()
        for label in ("alpha page", "beta page"):
            page = doc.new_page()
            page.insert_text((72, 72), label)
        path = tmp_path / "doc.pdf"
        path.write_bytes(doc.tobytes())
        doc.close()
        return path

    def test_xlsx_unknown_option_did_you_mean(
        self, tmp_path: Path, sample_xlsx_bytes: bytes
    ):
        file_path = tmp_path / "data.xlsx"
        file_path.write_bytes(sample_xlsx_bytes)

        result = att(f"{file_path}[sheets: 0]")

        warnings = result[0]["meta"]["warnings"]
        assert warnings == ["Unknown option 'sheets' for .xlsx — did you mean 'sheet'?"]
        # The bad key is dropped; processing still succeeds
        assert "error" not in result[0]["meta"]
        assert "Alice" in result[0]["text"]

    def test_pdf_dsl_pages_selects_single_page(self, two_page_pdf_path: Path):
        result = att(f"{two_page_pdf_path}[pages: 1-1, images: false]")

        assert "error" not in result[0]["meta"]
        assert "alpha page" in result[0]["text"]
        assert "beta page" not in result[0]["text"]

    def test_explicit_kwargs_override_dsl_pages(self, two_page_pdf_path: Path):
        result = att(f"{two_page_pdf_path}[pages: 1-1]", pages="2-3", images=False)

        assert "error" not in result[0]["meta"]
        assert "beta page" in result[0]["text"]
        assert "alpha page" not in result[0]["text"]

    def test_no_warnings_key_when_options_resolve_cleanly(
        self, two_page_pdf_path: Path
    ):
        """meta.warnings is ABSENT (not empty) when nothing went wrong."""
        result = att(f"{two_page_pdf_path}[pages: 1-1, images: false]")

        assert "warnings" not in result[0]["meta"]

    def test_mixed_directory_warns_per_file(
        self, tmp_path: Path, sample_text_bytes: bytes
    ):
        """A directory option applies per file: unknown for .txt, even
        though it would be valid for .pdf — warnings are per-processor."""
        (tmp_path / "note.txt").write_bytes(sample_text_bytes)

        result = att(f"{tmp_path}[pages: 1-2]")

        by_source = {a["meta"]["source"]: a for a in result}
        assert by_source["note.txt"]["meta"]["warnings"] == [
            "Unknown option 'pages' for .txt"
        ]

    def test_no_processor_means_no_option_warnings(
        self, tmp_path: Path, sample_binary_bytes: bytes
    ):
        file_path = tmp_path / "binary.bin"
        file_path.write_bytes(sample_binary_bytes)

        result = att(f"{file_path}[pages: 1-2]")

        meta = result[0]["meta"]
        assert meta["note"] == "no processor available"
        assert "warnings" not in meta


class TestAttErrorCodes:
    """Errors come back as artifacts with typed meta.error codes."""

    def test_unpack_failure_uses_unpack_error_code(self):
        result = att("/nonexistent/path/file.pdf")

        assert len(result) == 1
        error = result[0]["meta"]["error"]
        assert error["code"] == ERROR_UNPACK
        assert "unpack failed" in error["message"]

    def test_service_only_without_key_uses_service_error_code(
        self, tmp_path: Path, sample_text_bytes: bytes
    ):
        file_path = tmp_path / "test.txt"
        file_path.write_bytes(sample_text_bytes)

        result = att(str(file_path), prefer="service-only")

        assert len(result) == 1
        error = result[0]["meta"]["error"]
        assert error["code"] == ERROR_SERVICE
        assert "no service configured" in error["message"]

    def test_parse_failure_uses_parse_error_code(self, tmp_path: Path):
        @register_processor(".bad")
        def _parse_fails(data: bytes, **_opts):
            return error_artifact("broken.bad", ERROR_PARSE, "cannot parse")

        file_path = tmp_path / "broken.bad"
        file_path.write_bytes(b"\x00\x01garbage")

        result = att(str(file_path))

        assert result[0]["meta"]["error"]["code"] == ERROR_PARSE

    def test_error_artifact_has_correct_structure(self):
        result = att("/nonexistent/path/file.pdf")

        artifact = result[0]
        assert artifact["text"] == ""
        assert artifact["images"] == []
        assert artifact["audio"] == []
        assert artifact["video"] == []
        assert "meta" in artifact


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


class TestAttWithBinaryFiles:
    """Tests for att() with binary/non-text files."""

    def test_binary_file_no_processor(self, tmp_path: Path, sample_binary_bytes: bytes):
        file_path = tmp_path / "binary.bin"
        file_path.write_bytes(sample_binary_bytes)

        result = att(str(file_path))

        assert len(result) == 1
        # No processor for .bin: empty artifact with a note (not an error)
        meta = result[0]["meta"]
        assert meta["note"] == "no processor available"
        assert "error" not in meta
        assert result[0]["text"] == ""


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
