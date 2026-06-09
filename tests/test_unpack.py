"""
Tests for the unpack module - source resolution and archive handling.

=============================================================================
TEST GUIDELINES FOR UNPACK
=============================================================================

GOOD tests for unpack:
    - Test each source type: local file, directory, ZIP, TAR, HTTP, GitHub
    - Test archive expansion (nested archives)
    - Test path sanitization (prevent traversal attacks)
    - Test custom handler registration
    - Use tmp_path for file fixtures (auto-cleanup)

BAD tests for unpack:
    - Making real HTTP requests (use mocking or skip)
    - Making real git clones (slow, network-dependent)
    - Testing internal functions when public API suffices
    - Creating test files in the repo directory

NOTES:
    - HTTP and GitHub tests should mock or skip unless integration testing
    - Archive tests use fixtures from conftest.py
    - Always test path traversal prevention

=============================================================================
"""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from attachments.unpack import (
    RAW_ARCHIVE_SUFFIXES,
    _filename_from_content_disposition,
    _is_github_repo_root_url,
    _is_raw_archive_name,
    _is_zip_bytes,
    _sanitize_member_name,
    extra_unpack_handlers,
    register_unpack_handler,
    source,
    unpack,
)


class TestIsRawArchiveName:
    """Tests for _is_raw_archive_name - determines if file should be expanded."""

    @pytest.mark.parametrize(
        "filename",
        [
            "archive.zip",
            "backup.tar",
            "data.tar.gz",
            "files.tgz",
            "archive.tar.bz2",
            "archive.tbz2",
            "archive.tar.xz",
            "archive.txz",
        ],
    )
    def test_raw_archives_detected(self, filename: str):
        assert _is_raw_archive_name(filename) is True

    @pytest.mark.parametrize(
        "filename",
        [
            "document.xlsx",  # ZIP-based but not raw
            "presentation.pptx",
            "document.docx",
            "file.pdf",
            "image.png",
            "script.py",
        ],
    )
    def test_non_raw_files_not_detected(self, filename: str):
        assert _is_raw_archive_name(filename) is False

    def test_case_insensitive(self):
        assert _is_raw_archive_name("FILE.ZIP") is True
        assert _is_raw_archive_name("Archive.TAR.GZ") is True

    def test_all_suffixes_covered(self):
        """Every suffix in RAW_ARCHIVE_SUFFIXES should be detected."""
        for suffix in RAW_ARCHIVE_SUFFIXES:
            assert _is_raw_archive_name(f"test{suffix}") is True


class TestSanitizeMemberName:
    """Tests for _sanitize_member_name - prevents path traversal."""

    def test_normal_path_unchanged(self):
        assert _sanitize_member_name("path/to/file.txt") == "path/to/file.txt"

    def test_removes_leading_slash(self):
        assert _sanitize_member_name("/absolute/path.txt") == "absolute/path.txt"

    def test_removes_multiple_leading_slashes(self):
        assert _sanitize_member_name("///path.txt") == "path.txt"

    def test_removes_parent_traversal(self):
        assert _sanitize_member_name("../../../etc/passwd") == "etc/passwd"

    def test_removes_dot_segments(self):
        assert _sanitize_member_name("./current/./file.txt") == "current/file.txt"

    def test_converts_backslashes(self):
        assert (
            _sanitize_member_name("windows\\path\\file.txt") == "windows/path/file.txt"
        )

    def test_complex_traversal_attack(self):
        result = _sanitize_member_name("foo/../../../etc/passwd")
        assert ".." not in result
        assert result == "foo/etc/passwd"

    def test_empty_segments_removed(self):
        assert _sanitize_member_name("a//b///c.txt") == "a/b/c.txt"


class TestIsZipBytes:
    """Tests for _is_zip_bytes - detects ZIP file signature."""

    def test_valid_zip_signature(self):
        assert _is_zip_bytes(b"PK\x03\x04rest of file") is True

    def test_empty_bytes(self):
        assert _is_zip_bytes(b"") is False

    def test_non_zip_content(self):
        assert _is_zip_bytes(b"Hello World") is False

    def test_pdf_not_detected_as_zip(self):
        assert _is_zip_bytes(b"%PDF-1.4") is False


class TestIsGithubRepoRootUrl:
    """Tests for _is_github_repo_root_url."""

    def test_simple_repo_url(self):
        assert _is_github_repo_root_url("https://github.com/owner/repo") is True

    def test_repo_with_git_suffix(self):
        assert _is_github_repo_root_url("https://github.com/owner/repo.git") is True

    def test_repo_with_query_params(self):
        assert (
            _is_github_repo_root_url("https://github.com/owner/repo?ref=main") is True
        )

    def test_file_path_not_repo_root(self):
        assert (
            _is_github_repo_root_url("https://github.com/owner/repo/blob/main/file.py")
            is False
        )

    def test_non_github_url(self):
        assert _is_github_repo_root_url("https://gitlab.com/owner/repo") is False

    def test_http_not_https(self):
        assert _is_github_repo_root_url("http://github.com/owner/repo") is False


class TestFilenameFromContentDisposition:
    """Tests for _filename_from_content_disposition."""

    def test_simple_filename(self):
        result = _filename_from_content_disposition('attachment; filename="report.pdf"')
        assert result == "report.pdf"

    def test_unquoted_filename(self):
        result = _filename_from_content_disposition("attachment; filename=data.csv")
        assert result == "data.csv"

    def test_none_returns_none(self):
        assert _filename_from_content_disposition(None) is None

    def test_empty_returns_none(self):
        assert _filename_from_content_disposition("") is None

    def test_no_filename_in_header(self):
        result = _filename_from_content_disposition("attachment")
        assert result is None


class TestUnpackLocalFile:
    """Tests for unpacking local files."""

    def test_unpack_text_file(self, tmp_path: Path, sample_text_bytes: bytes):
        file_path = tmp_path / "test.txt"
        file_path.write_bytes(sample_text_bytes)

        result = unpack(str(file_path))

        assert len(result) == 1
        name, data = result[0]
        assert name == "test.txt"
        assert data == sample_text_bytes

    def test_unpack_nonexistent_file_raises(self):
        with pytest.raises(ValueError, match="non-existent"):
            unpack("/nonexistent/path/file.txt")


class TestUnpackDirectory:
    """Tests for unpacking directories."""

    def test_unpack_directory(self, sample_directory: Path):
        result = unpack(str(sample_directory))
        names = {name for name, _ in result}

        assert "readme.txt" in names
        assert "data.json" in names
        assert "subdir/nested.md" in names or "nested.md" in str(names)

    def test_skips_git_directory(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_bytes(b"git config")
        (tmp_path / "real_file.txt").write_bytes(b"content")

        result = unpack(str(tmp_path))
        names = {name for name, _ in result}

        assert "real_file.txt" in names
        assert not any(".git" in name for name in names)


class TestUnpackZip:
    """Tests for unpacking ZIP archives."""

    def test_unpack_zip_file(self, tmp_path: Path, sample_zip_bytes: bytes):
        zip_path = tmp_path / "archive.zip"
        zip_path.write_bytes(sample_zip_bytes)

        result = unpack(str(zip_path))

        assert len(result) == 1
        name, data = result[0]
        assert "hello.txt" in name
        assert b"Hello" in data

    def test_unpack_nested_zip(self, tmp_path: Path, nested_zip_bytes: bytes):
        zip_path = tmp_path / "nested.zip"
        zip_path.write_bytes(nested_zip_bytes)

        result = unpack(str(zip_path))
        names = {name for name, _ in result}

        # Should have expanded both levels
        assert any("outer.txt" in name for name in names)
        assert any("deep.txt" in name for name in names)

    def test_zip_path_traversal_sanitized(
        self, tmp_path: Path, zip_with_traversal_attempt: bytes
    ):
        zip_path = tmp_path / "malicious.zip"
        zip_path.write_bytes(zip_with_traversal_attempt)

        result = unpack(str(zip_path))
        names = {name for name, _ in result}

        # No path should contain .. or start with /
        for name in names:
            assert ".." not in name
            assert not name.startswith("/")


class TestUnpackTar:
    """Tests for unpacking TAR archives."""

    def test_unpack_tar_file(self, tmp_path: Path, sample_text_bytes: bytes):
        # Create a tar file
        tar_path = tmp_path / "archive.tar"
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            info = tarfile.TarInfo(name="file.txt")
            info.size = len(sample_text_bytes)
            tf.addfile(info, io.BytesIO(sample_text_bytes))
        tar_path.write_bytes(buf.getvalue())

        result = unpack(str(tar_path))

        assert len(result) == 1
        name, data = result[0]
        assert "file.txt" in name
        assert data == sample_text_bytes

    def test_unpack_tar_gz(self, tmp_path: Path, sample_text_bytes: bytes):
        tar_path = tmp_path / "archive.tar.gz"
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            info = tarfile.TarInfo(name="compressed.txt")
            info.size = len(sample_text_bytes)
            tf.addfile(info, io.BytesIO(sample_text_bytes))
        tar_path.write_bytes(buf.getvalue())

        result = unpack(str(tar_path))

        assert len(result) == 1
        assert b"Hello" in result[0][1]


class TestRegisterUnpackHandler:
    """Tests for custom handler registration."""

    def test_register_function(self):
        def my_handler(url: str) -> list[tuple[str, bytes]]:
            return [("test.txt", b"from handler")]

        register_unpack_handler("myproto://", my_handler)

        try:
            assert "myproto://" in extra_unpack_handlers
            result = unpack("myproto://something")
            assert result == [("test.txt", b"from handler")]
        finally:
            # Cleanup
            del extra_unpack_handlers["myproto://"]

    def test_register_decorator(self):
        @register_unpack_handler("decorated://")
        def decorated_handler(url: str) -> list[tuple[str, bytes]]:
            return [("decorated.txt", b"decorated")]

        try:
            assert "decorated://" in extra_unpack_handlers
        finally:
            del extra_unpack_handlers["decorated://"]


class TestSourceDecorator:
    """Tests for @source decorator (multiple prefixes)."""

    def test_source_multiple_prefixes(self):
        @source("multi1://", "multi2://")
        def multi_handler(url: str) -> list[tuple[str, bytes]]:
            return [("multi.txt", b"multi")]

        try:
            assert "multi1://" in extra_unpack_handlers
            assert "multi2://" in extra_unpack_handlers
        finally:
            del extra_unpack_handlers["multi1://"]
            del extra_unpack_handlers["multi2://"]


class TestUnpackIntegration:
    """Integration tests for unpack with directories containing archives."""

    def test_directory_with_zip_expansion(self, sample_directory_with_zip: Path):
        result = unpack(str(sample_directory_with_zip))
        names = {name for name, _ in result}

        # Regular files from directory
        assert "readme.txt" in names

        # Files from the ZIP should be expanded
        assert any("archive.zip/" in name and "hello.txt" in name for name in names)

    def test_xlsx_not_expanded(self, tmp_path: Path):
        """XLSX files (ZIP-based) should NOT be expanded as archives."""
        # Create a fake xlsx (just for testing - not valid xlsx)
        xlsx_path = tmp_path / "data.xlsx"
        xlsx_path.write_bytes(b"PK\x03\x04not a real xlsx but has zip sig")

        result = unpack(str(tmp_path))
        names = {name for name, _ in result}

        # Should appear as single file, not expanded
        assert "data.xlsx" in names
        assert not any("data.xlsx/" in name for name in names)
