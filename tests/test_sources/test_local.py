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

        # Same order as a folder: a folder's files, then its subfolders.
        assert names == ["top.md", "sub/nested.md"]

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
        assert ".gitignore" not in names  # hidden files are skipped by default
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

    def test_negation_brings_a_file_back(self, tmp_path: Path):
        (tmp_path / ".gitignore").write_text("*.log\n!keep.log\n")
        (tmp_path / "keep.log").write_bytes(b"k")
        (tmp_path / "drop.log").write_bytes(b"d")
        (tmp_path / "other.txt").write_bytes(b"o")

        names = {name for name, _ in unpack(str(tmp_path))}

        assert names == {"keep.log", "other.txt"}

    def test_anchored_pattern_only_excludes_at_root(self, tmp_path: Path):
        (tmp_path / ".gitignore").write_text("/anchored.txt\n")
        (tmp_path / "anchored.txt").write_bytes(b"r")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "anchored.txt").write_bytes(b"s")

        names = {name for name, _ in unpack(str(tmp_path))}

        assert "anchored.txt" not in names
        assert "sub/anchored.txt" in names

    def test_nested_gitignore_applies_to_its_folder(self, tmp_path: Path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / ".gitignore").write_text("*.log\n")
        (tmp_path / "sub" / "app.log").write_bytes(b"l")
        (tmp_path / "top.log").write_bytes(b"t")

        names = {name for name, _ in unpack(str(tmp_path))}

        assert names == {"top.log"}

    def test_no_gitignore_behavior_unchanged(self, tmp_path: Path):
        (tmp_path / "app.log").write_bytes(b"l")
        (tmp_path / "build").mkdir()
        (tmp_path / "build" / "out.txt").write_bytes(b"o")

        names = [name for name, _ in unpack(str(tmp_path))]

        assert names == ["app.log", "build/out.txt"]


# =============================================================================
# Folder options, limits and safety (resolve(): files + report)
# =============================================================================

import io as _io  # noqa: E402
import os as _os  # noqa: E402
import zipfile as _zipfile  # noqa: E402

from attachments._sources import InvalidSourceOption, resolve  # noqa: E402


def _tree(root: Path, files: dict[str, bytes | str]) -> Path:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode() if isinstance(content, str) else content)
    return root


class TestDefaultSkips:
    def test_project_folder(self, tmp_path: Path):
        _tree(
            tmp_path,
            {
                "app.py": "x",
                ".env": "SECRET=1",
                ".env.example": "SECRET=",
                "node_modules/dep/index.js": "x",
                "package-lock.json": "{}",
                ".github/workflows/ci.yml": "on: push",
                "venv/pyvenv.cfg": "home=/usr",
                "venv/lib/site.py": "x",
                "build/out.js": "x",  # no .gitignore: kept
            },
        )
        res = resolve(str(tmp_path))
        assert [n for n, _ in res.files] == ["app.py", "build/out.js"]
        skipped = res.reports[0].skipped
        assert skipped["secret"].examples == [".env"]
        assert skipped["generated"].folders == 2  # node_modules, venv
        assert skipped["hidden"].files == 1  # .env.example is hidden
        assert skipped["hidden"].folders == 1  # .github

    def test_hidden_true(self, tmp_path: Path):
        _tree(tmp_path, {".github/ci.yml": "x", ".env": "s", "a.py": "x"})
        names = [n for n, _ in resolve(str(tmp_path), options={"hidden": True}).files]
        assert names == ["a.py", ".github/ci.yml"]  # still no .env

    def test_ignore_none(self, tmp_path: Path):
        _tree(tmp_path, {".env": "s", "uv.lock": "x", ".git/HEAD": "ref"})
        names = {n for n, _ in resolve(str(tmp_path), options={"ignore": "none"}).files}
        assert names == {".env", "uv.lock"}  # never .git

    def test_ignore_patterns_and_glob(self, tmp_path: Path):
        _tree(tmp_path, {"a.py": "", "b.md": "", "tests/t.py": "", "c.csv": ""})
        res = resolve(str(tmp_path), options={"ignore": "tests/", "glob": "*.py, *.md"})
        assert [n for n, _ in res.files] == ["a.py", "b.md"]

    def test_not_recursive(self, tmp_path: Path):
        _tree(tmp_path, {"a.txt": "", "sub/b.txt": ""})
        res = resolve(str(tmp_path), options={"recursive": False})
        assert [n for n, _ in res.files] == ["a.txt"]


class TestLimits:
    def test_max_files_keeps_order_and_counts_the_rest(self, tmp_path: Path):
        _tree(tmp_path, {f"f{i:02}.txt": "x" for i in range(10)})
        res = resolve(str(tmp_path), options={"max_files": 3})
        assert [n for n, _ in res.files] == ["f00.txt", "f01.txt", "f02.txt"]
        report = res.reports[0]
        assert report.limit == "max_files" and report.not_read == 7

    def test_max_size_skips_big_files_but_keeps_reading(self, tmp_path: Path):
        _tree(tmp_path, {"a.txt": "x" * 10, "big.bin": "x" * 1000, "c.txt": "x" * 10})
        res = resolve(str(tmp_path), options={"max_size": "100B"})
        assert [n for n, _ in res.files] == ["a.txt", "c.txt"]
        assert res.reports[0].limit == "max_size"

    def test_zero_means_no_limit(self, tmp_path: Path):
        _tree(tmp_path, {f"f{i}.txt": "x" for i in range(5)})
        res = resolve(str(tmp_path), options={"max_files": 0, "max_size": 0})
        assert len(res.files) == 5 and res.reports[0].limit is None

    def test_invalid_values_raise_typed_errors(self, tmp_path: Path):
        with pytest.raises(InvalidSourceOption, match="max_size"):
            resolve(str(tmp_path), options={"max_size": "lots"})
        with pytest.raises(InvalidSourceOption, match="max_files"):
            resolve(str(tmp_path), options={"max_files": -1})

    def test_files_false_reads_nothing(self, tmp_path: Path):
        _tree(tmp_path, {"a.txt": "x", "sub/b.txt": "y"})
        res = resolve(str(tmp_path), options={"files": False})
        assert res.files == []
        assert [e.path for e in res.reports[0].entries] == ["a.txt", "sub/b.txt"]

    def test_scan_cap(self, tmp_path: Path, monkeypatch):
        import attachments._sources.local as local

        monkeypatch.setattr(local, "MAX_SCAN_ENTRIES", 3)
        _tree(tmp_path, {f"f{i}.txt": "x" for i in range(10)})
        res = resolve(str(tmp_path))
        assert res.reports[0].scan_capped is True
        assert len(res.files) == 3


class TestSafety:
    @pytest.mark.skipif(not hasattr(_os, "symlink"), reason="no symlinks")
    def test_links_outside_the_folder_are_not_followed(self, tmp_path: Path):
        outside = tmp_path / "outside"
        _tree(outside, {"id_rsa_copy": "PRIVATE"})
        inside = tmp_path / "repo"
        _tree(inside, {"a.txt": "x", "real.txt": "inside"})
        (inside / "leak.txt").symlink_to(outside / "id_rsa_copy")
        (inside / "alias.txt").symlink_to(inside / "real.txt")
        (inside / "outdir").symlink_to(outside, target_is_directory=True)
        res = resolve(str(inside))
        names = [n for n, _ in res.files]
        assert "leak.txt" not in names and not any("outdir" in n for n in names)
        assert "alias.txt" in names  # a link inside the folder is fine
        links = res.reports[0].skipped["link outside the folder"].examples
        assert links == ["leak.txt", "outdir"]

    @pytest.mark.skipif(not hasattr(_os, "mkfifo"), reason="no named pipes")
    def test_named_pipes_are_not_read(self, tmp_path: Path):
        _tree(tmp_path, {"a.txt": "x"})
        _os.mkfifo(tmp_path / "pipe")
        res = resolve(str(tmp_path))  # would block forever if read
        assert [n for n, _ in res.files] == ["a.txt"]
        assert res.reports[0].skipped["not a regular file"].files == 1


def _zip(files: dict[str, str]) -> bytes:
    buf = _io.BytesIO()
    with _zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


class TestArchives:
    def test_archive_members_get_the_same_rules(self, tmp_path: Path):
        data = _zip(
            {
                "proj/.gitignore": "dist/\n",
                "proj/app.py": "x",
                "proj/.env": "SECRET",
                "proj/dist/bundle.js": "x",
                "proj/node_modules/d/i.js": "x",
            }
        )
        (tmp_path / "proj.zip").write_bytes(data)
        res = resolve(str(tmp_path / "proj.zip"))
        assert [n for n, _ in res.files] == ["proj.zip/proj/app.py"]
        assert res.reports[0].kind == "archive"

    def test_archive_in_a_folder_counts_members_toward_limits(self, tmp_path: Path):
        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "b.zip").write_bytes(_zip({f"m{i}.txt": "x" for i in range(5)}))
        res = resolve(str(tmp_path), options={"max_files": 3})
        assert [n for n, _ in res.files] == ["a.txt", "b.zip/m0.txt", "b.zip/m1.txt"]


class TestPatterns:
    def test_wildcard_in_the_middle(self, tmp_path: Path):
        _tree(tmp_path, {"g/one/x.py": "1", "g/two/x.py": "2", "g/two/y.py": "3"})
        names = [n for n, _ in unpack(str(tmp_path / "g" / "*" / "x.py"))]
        assert names == ["one/x.py", "two/x.py"]

    def test_patterns_respect_the_skip_rules(self, tmp_path: Path):
        _tree(tmp_path, {"src/a.js": "", "node_modules/d/i.js": "", ".cache/c.js": ""})
        names = [n for n, _ in unpack(str(tmp_path / "**" / "*.js"))]
        assert names == ["src/a.js"]

    def test_explicit_dot_component_reaches_hidden_folders(self, tmp_path: Path):
        _tree(tmp_path, {".github/workflows/ci.yml": "on: push"})
        names = [n for n, _ in unpack(str(tmp_path / ".github" / "**" / "*.yml"))]
        assert names == ["workflows/ci.yml"]

    def test_no_match_explains_skipped_files(self, tmp_path: Path):
        _tree(tmp_path, {"server.pem": "s", "client.pem": "s"})
        with pytest.raises(ValueError, match=r"secret: 2.*ignore: none"):
            unpack(str(tmp_path / "*.pem"))


class TestPathForms:
    def test_file_uri(self, tmp_path: Path):
        (tmp_path / "a b.txt").write_text("hi")
        uri = (tmp_path / "a b.txt").as_uri()
        assert unpack(uri) == [("a b.txt", b"hi")]

    def test_file_uri_with_a_host_is_refused(self):
        with pytest.raises(ValueError, match="local file"):
            unpack("file://server/share/a.txt")

    def test_tilde(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / "notes.txt").write_text("n")
        assert unpack("~/notes.txt") == [("notes.txt", b"n")]

    def test_single_named_secret_file_is_read(self, tmp_path: Path):
        # Naming one file is explicit: no skip rules.
        (tmp_path / ".env").write_text("A=1")
        assert unpack(str(tmp_path / ".env")) == [(".env", b"A=1")]


def test_invalid_character_range_is_literal_not_a_crash(tmp_path: Path):
    (tmp_path / "a[x-f].txt").write_text("odd")
    (tmp_path / "b.txt").write_text("b")
    # "[x-f]" is not a valid set (x > f): a literal bracket, no regex error.
    assert unpack(str(tmp_path / "*[x-f]*")) == [("a[x-f].txt", b"odd")]


@pytest.mark.skipif(
    not hasattr(_os, "geteuid") or _os.geteuid() == 0, reason="needs a non-root user"
)
def test_unreadable_folders_are_reported_not_fatal(tmp_path: Path):
    _tree(tmp_path, {"a.txt": "x", "locked/b.txt": "y"})
    (tmp_path / "locked").chmod(0o000)
    try:
        res = resolve(str(tmp_path))
    finally:
        (tmp_path / "locked").chmod(0o755)
    assert [n for n, _ in res.files] == ["a.txt"]
    assert res.reports[0].skipped["unreadable"].folders == 1


def test_malformed_dsl_block_is_explained(tmp_path: Path):
    page = tmp_path / "page.html"
    page.write_text("<h1>x</h1>")
    with pytest.raises(ValueError, match="is not a valid DSL options block"):
        unpack(f"{page}[h1, select: p]")  # must start with "key: value"
    with pytest.raises(ValueError, match=r"are options: att\(\) reads them"):
        unpack(f"{page}[select: h1,p]")  # valid options, given to unpack()


def test_archive_overview_only(tmp_path: Path):
    (tmp_path / "b.zip").write_bytes(_zip({"x/a.txt": "1", "x/.env": "s"}))
    res = resolve(str(tmp_path / "b.zip"), options={"files": False})
    assert res.files == [] and [e.path for e in res.reports[0].entries] == ["x/a.txt"]


def test_no_match_counts_only_what_the_pattern_could_match(tmp_path: Path):
    _tree(tmp_path, {".hidden/x.txt": "", "node_modules/y.js": "", "a.md": ""})
    with pytest.raises(ValueError) as info:
        unpack(str(tmp_path / "*.pdf"))
    assert "skipped" not in str(info.value)  # nothing skipped could have matched
