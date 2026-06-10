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


class TestUnpackGlob:
    """Tests for glob-pattern inputs."""

    def test_glob_txt_sorted_and_stable(self, tmp_path: Path):
        for name in ("zeta.txt", "alpha.txt", "mid.txt", "skip.md"):
            (tmp_path / name).write_bytes(b"x")

        pattern = str(tmp_path / "*.txt")
        names = [name for name, _ in unpack(pattern)]

        assert names == ["alpha.txt", "mid.txt", "zeta.txt"]
        # Stable across calls.
        assert names == [name for name, _ in unpack(pattern)]

    def test_glob_recursive_md(self, tmp_path: Path):
        (tmp_path / "top.md").write_bytes(b"t")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "nested.md").write_bytes(b"n")
        (tmp_path / "sub" / "other.txt").write_bytes(b"o")

        names = [name for name, _ in unpack(str(tmp_path / "**" / "*.md"))]

        assert names == ["sub/nested.md", "top.md"]

    def test_glob_names_relative_to_static_base(self, tmp_path: Path):
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "b").mkdir()
        (tmp_path / "a" / "b" / "deep.txt").write_bytes(b"d")

        # Static base is tmp_path/a — names relative to it.
        names = [name for name, _ in unpack(str(tmp_path / "a" / "**" / "*.txt"))]
        assert names == ["b/deep.txt"]

    def test_glob_zero_matches_raises_with_pattern(self, tmp_path: Path):
        pattern = str(tmp_path / "*.nomatch")
        with pytest.raises(ValueError, match="matched no files"):
            unpack(pattern)
        try:
            unpack(pattern)
        except ValueError as e:
            assert pattern in str(e)

    def test_literal_file_with_brackets_wins_over_glob(self, tmp_path: Path):
        """A file literally named file[1].txt resolves as a file (v1 edge case 8)."""
        (tmp_path / "file[1].txt").write_bytes(b"literal")

        result = unpack(str(tmp_path / "file[1].txt"))

        assert result == [("file[1].txt", b"literal")]

    def test_glob_matched_zip_expands(self, tmp_path: Path, sample_zip_bytes: bytes):
        (tmp_path / "archive.zip").write_bytes(sample_zip_bytes)

        names = [name for name, _ in unpack(str(tmp_path / "*.zip"))]

        assert any("archive.zip/" in n and "hello.txt" in n for n in names)


class TestGitignoreWalk:
    """Tests for gitignore-aware directory walks (top-level .gitignore only)."""

    def test_log_and_build_excluded_siblings_survive(self, tmp_path: Path):
        (tmp_path / ".gitignore").write_text("*.log\nbuild/\n")
        (tmp_path / "app.log").write_bytes(b"l")
        (tmp_path / "app.py").write_bytes(b"p")
        (tmp_path / "build").mkdir()
        (tmp_path / "build" / "out.txt").write_bytes(b"o")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_bytes(b"m")

        names = {name for name, _ in unpack(str(tmp_path))}

        assert "app.py" in names
        assert "src/main.py" in names
        assert ".gitignore" in names  # stays unless a pattern excludes it
        assert "app.log" not in names
        assert not any(name.startswith("build/") for name in names)

    def test_dir_pattern_prunes_nested_content(self, tmp_path: Path):
        (tmp_path / ".gitignore").write_text("node_modules/\n")
        nm = tmp_path / "pkg" / "node_modules" / "dep"
        nm.mkdir(parents=True)
        (nm / "index.js").write_bytes(b"j")
        (tmp_path / "pkg" / "main.js").write_bytes(b"m")

        names = {name for name, _ in unpack(str(tmp_path))}

        assert "pkg/main.js" in names
        assert not any("node_modules" in name for name in names)

    def test_negation_line_skipped_keep_log_stays_excluded(self, tmp_path: Path):
        """'!' negation is unsupported: the line is skipped entirely."""
        (tmp_path / ".gitignore").write_text("*.log\n!keep.log\n")
        (tmp_path / "keep.log").write_bytes(b"k")
        (tmp_path / "other.txt").write_bytes(b"o")

        names = {name for name, _ in unpack(str(tmp_path))}

        assert "keep.log" not in names  # negation NOT honored
        assert "other.txt" in names

    def test_anchored_pattern_only_excludes_at_root(self, tmp_path: Path):
        (tmp_path / ".gitignore").write_text("/anchored.txt\n")
        (tmp_path / "anchored.txt").write_bytes(b"r")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "anchored.txt").write_bytes(b"s")

        names = {name for name, _ in unpack(str(tmp_path))}

        assert "anchored.txt" not in names
        assert "sub/anchored.txt" in names

    def test_nested_gitignore_has_no_effect(self, tmp_path: Path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / ".gitignore").write_text("*.log\n")
        (tmp_path / "sub" / "app.log").write_bytes(b"l")

        names = {name for name, _ in unpack(str(tmp_path))}

        assert "sub/app.log" in names  # nested .gitignore ignored

    def test_no_gitignore_behavior_unchanged(self, tmp_path: Path):
        (tmp_path / "app.log").write_bytes(b"l")
        (tmp_path / "build").mkdir()
        (tmp_path / "build" / "out.txt").write_bytes(b"o")

        names = [name for name, _ in unpack(str(tmp_path))]

        assert names == ["app.log", "build/out.txt"]
