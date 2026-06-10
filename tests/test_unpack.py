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

import attachments._unpack as unpack_mod
from attachments._unpack import (
    RAW_ARCHIVE_SUFFIXES,
    _assert_public_http_url,
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

    def test_directory_walk_is_sorted_and_deterministic(self, tmp_path: Path):
        """Artifact order must not depend on filesystem internals.

        Raw os.walk order varies across filesystems and file-creation
        history, which would make .text / .chunk() / the repr differ
        machine-to-machine and break prompt caching.
        """
        # Create files in deliberately non-alphabetical order.
        for name in ("zeta.txt", "alpha.txt", "mid.txt"):
            (tmp_path / name).write_bytes(b"x")
        (tmp_path / "bdir").mkdir()
        (tmp_path / "bdir" / "two.txt").write_bytes(b"x")
        (tmp_path / "adir").mkdir()
        (tmp_path / "adir" / "one.txt").write_bytes(b"x")

        names = [name for name, _ in unpack(str(tmp_path))]

        # Top-level files first (sorted), then subdirectories sorted.
        assert names == [
            "alpha.txt",
            "mid.txt",
            "zeta.txt",
            "adir/one.txt",
            "bdir/two.txt",
        ]
        # And stable across calls.
        assert names == [name for name, _ in unpack(str(tmp_path))]

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


class TestArchiveBombGuards:
    """Decompression-bomb protection in _explode_archive_bytes."""

    def test_expansion_budget_enforced(self, tmp_path: Path, monkeypatch):
        """A tiny compressed file expanding past the cap raises ValueError."""
        monkeypatch.setattr(unpack_mod, "MAX_ARCHIVE_EXPANSION_BYTES", 64 * 1024)

        import zipfile as _zipfile

        buf = io.BytesIO()
        with _zipfile.ZipFile(buf, "w", _zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("big.bin", b"\0" * (10 * 1024 * 1024))  # ~10KB compressed
        bomb = tmp_path / "bomb.zip"
        bomb.write_bytes(buf.getvalue())

        with pytest.raises(ValueError, match="maximum total size"):
            unpack(str(bomb))

    def test_budget_shared_across_nested_archives(self, monkeypatch):
        monkeypatch.setattr(unpack_mod, "MAX_ARCHIVE_EXPANSION_BYTES", 1024)

        import zipfile as _zipfile

        inner = io.BytesIO()
        with _zipfile.ZipFile(inner, "w", _zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("a.bin", b"\0" * 800)
        outer = io.BytesIO()
        with _zipfile.ZipFile(outer, "w", _zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("one.zip", inner.getvalue())
            zf.writestr("b.bin", b"\0" * 800)

        with pytest.raises(ValueError, match="maximum total size"):
            unpack_mod._explode_archive_bytes("outer.zip", outer.getvalue())

    def test_nesting_depth_enforced(self, monkeypatch):
        monkeypatch.setattr(unpack_mod, "MAX_ARCHIVE_DEPTH", 1)

        import zipfile as _zipfile

        blob = b"payload"
        for i in range(3):  # zip-in-zip-in-zip
            buf = io.BytesIO()
            with _zipfile.ZipFile(buf, "w") as zf:
                name = "data.txt" if i == 0 else f"level{i}.zip"
                zf.writestr(name, blob)
            blob = buf.getvalue()

        with pytest.raises(ValueError, match="maximum depth"):
            unpack_mod._explode_archive_bytes("outer.zip", blob)

    def test_normal_archives_unaffected(self, tmp_path: Path, sample_zip_bytes: bytes):
        zip_path = tmp_path / "archive.zip"
        zip_path.write_bytes(sample_zip_bytes)
        result = unpack(str(zip_path))
        assert len(result) == 1
        assert b"Hello" in result[0][1]

    def test_tar_member_budget_enforced(self, monkeypatch):
        monkeypatch.setattr(unpack_mod, "MAX_ARCHIVE_EXPANSION_BYTES", 1024)

        payload = b"\0" * 4096
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            info = tarfile.TarInfo(name="big.bin")
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))

        with pytest.raises(ValueError, match="maximum total size"):
            unpack_mod._explode_archive_bytes("bomb.tar.gz", buf.getvalue())


class TestSsrfGuard:
    """_assert_public_http_url blocks private/internal addresses."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/admin",
            "http://localhost:8080/x",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.5/internal",
            "http://192.168.1.1/router",
            "http://[::1]/v6-loopback",
        ],
    )
    def test_blocks_non_public_addresses(self, url: str):
        with pytest.raises(ValueError, match="Blocked URL|Cannot resolve"):
            _assert_public_http_url(url)

    def test_blocks_non_http_schemes(self):
        with pytest.raises(ValueError, match="scheme"):
            _assert_public_http_url("ftp://example.com/file")

    def test_allows_public_literal_address(self):
        # 93.184.216.34 (example.com) is a public address; no DNS needed.
        _assert_public_http_url("http://93.184.216.34/page")

    def test_unpack_blocks_private_url_when_enabled(self):
        with pytest.raises(ValueError, match="non-public address"):
            unpack("http://127.0.0.1:9/secret.zip", block_private_urls=True)

    def test_guard_off_by_default_for_library_use(self, monkeypatch):
        """Without the flag, private URLs reach the downloader (no SSRF
        validation) — the library trusts its local caller by default."""
        seen = {}

        def fake_urlopen(req, timeout=None):
            seen["url"] = req.full_url
            raise OSError("stop before any network I/O")

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        with pytest.raises(OSError, match="stop before"):
            unpack_mod._download_http_or_https("http://127.0.0.1:9/x")
        assert seen["url"] == "http://127.0.0.1:9/x"


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
