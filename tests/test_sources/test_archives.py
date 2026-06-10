"""
Tests for archive sources - ZIP/TAR expansion and its security guards.

=============================================================================
TEST GUIDELINES FOR ARCHIVE SOURCES
=============================================================================

GOOD tests for archive sources:
    - Test ZIP and TAR expansion (including nested archives)
    - Test path sanitization (prevent traversal attacks)
    - Test the decompression-bomb guards (budget + depth)
    - Use tmp_path / conftest fixtures for archives (auto-cleanup)

BAD tests for archive sources:
    - Expanding zip-based document formats (.xlsx/.docx are NOT raw archives)
    - Creating test files in the repo directory

NOTES:
    - Archive fixtures live in tests/conftest.py
    - Always test path traversal prevention

=============================================================================
"""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

import attachments._sources.archives as archives_mod
from attachments._sources import unpack
from attachments._sources._guards import _sanitize_member_name
from attachments._sources.archives import (
    RAW_ARCHIVE_SUFFIXES,
    _is_raw_archive_name,
    _is_zip_bytes,
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


class TestArchiveBombGuards:
    """Decompression-bomb protection in _explode_archive_bytes."""

    def test_expansion_budget_enforced(self, tmp_path: Path, monkeypatch):
        """A tiny compressed file expanding past the cap raises ValueError."""
        monkeypatch.setattr(archives_mod, "MAX_ARCHIVE_EXPANSION_BYTES", 64 * 1024)

        import zipfile as _zipfile

        buf = io.BytesIO()
        with _zipfile.ZipFile(buf, "w", _zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("big.bin", b"\0" * (10 * 1024 * 1024))  # ~10KB compressed
        bomb = tmp_path / "bomb.zip"
        bomb.write_bytes(buf.getvalue())

        with pytest.raises(ValueError, match="maximum total size"):
            unpack(str(bomb))

    def test_budget_shared_across_nested_archives(self, monkeypatch):
        monkeypatch.setattr(archives_mod, "MAX_ARCHIVE_EXPANSION_BYTES", 1024)

        import zipfile as _zipfile

        inner = io.BytesIO()
        with _zipfile.ZipFile(inner, "w", _zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("a.bin", b"\0" * 800)
        outer = io.BytesIO()
        with _zipfile.ZipFile(outer, "w", _zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("one.zip", inner.getvalue())
            zf.writestr("b.bin", b"\0" * 800)

        with pytest.raises(ValueError, match="maximum total size"):
            archives_mod._explode_archive_bytes("outer.zip", outer.getvalue())

    def test_nesting_depth_enforced(self, monkeypatch):
        monkeypatch.setattr(archives_mod, "MAX_ARCHIVE_DEPTH", 1)

        import zipfile as _zipfile

        blob = b"payload"
        for i in range(3):  # zip-in-zip-in-zip
            buf = io.BytesIO()
            with _zipfile.ZipFile(buf, "w") as zf:
                name = "data.txt" if i == 0 else f"level{i}.zip"
                zf.writestr(name, blob)
            blob = buf.getvalue()

        with pytest.raises(ValueError, match="maximum depth"):
            archives_mod._explode_archive_bytes("outer.zip", blob)

    def test_normal_archives_unaffected(self, tmp_path: Path, sample_zip_bytes: bytes):
        zip_path = tmp_path / "archive.zip"
        zip_path.write_bytes(sample_zip_bytes)
        result = unpack(str(zip_path))
        assert len(result) == 1
        assert b"Hello" in result[0][1]

    def test_tar_member_budget_enforced(self, monkeypatch):
        monkeypatch.setattr(archives_mod, "MAX_ARCHIVE_EXPANSION_BYTES", 1024)

        payload = b"\0" * 4096
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            info = tarfile.TarInfo(name="big.bin")
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))

        with pytest.raises(ValueError, match="maximum total size"):
            archives_mod._explode_archive_bytes("bomb.tar.gz", buf.getvalue())
