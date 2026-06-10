"""
Tests for local sources - single files and deterministic directory walks.

=============================================================================
TEST GUIDELINES FOR LOCAL SOURCES
=============================================================================

GOOD tests for local sources:
    - Test single files and directory walks via the public unpack()
    - Test the deterministic (sorted) walk order guarantee
    - Test VCS/cache directory pruning (.git, __pycache__, ...)
    - Use tmp_path for file fixtures (auto-cleanup)

BAD tests for local sources:
    - Creating test files in the repo directory
    - Testing archive internals here (that's test_archives.py)

=============================================================================
"""

from __future__ import annotations

from pathlib import Path

import pytest

from attachments._sources import unpack


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
