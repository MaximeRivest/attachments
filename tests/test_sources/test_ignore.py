"""Tests for the skip rules (``_sources/_ignore.py``).

The gitignore matcher is checked against git itself: for each case, a
real repository is created and ``git check-ignore`` is asked about every
path; our engine must agree on all of them.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from attachments._sources._ignore import (
    GENERATED,
    HIDDEN,
    IGNORE_FILE,
    OPTION,
    SECRET,
    VCS,
    IgnoreEngine,
    is_secret,
)
from attachments._sources.local import TreeOptions, folder_engine

# (ignore files {folder: text}, paths to check — folders end with "/")
GIT_CASES = [
    ({"": "*.log\n"}, ["a.log", "sub/b.log", "a.txt", "sub/"]),
    ({"": "/root.txt\n"}, ["root.txt", "sub/root.txt"]),
    ({"": "build/\n"}, ["build/", "src/build/", "build.txt"]),
    ({"": "doc/*.txt\n"}, ["doc/a.txt", "doc/sub/a.txt", "x/doc/a.txt"]),
    ({"": "**/logs\n"}, ["logs/", "a/b/logs/", "logs.txt"]),
    ({"": "a/**/b\n"}, ["a/b", "a/x/b", "a/x/y/b", "c/a/b"]),
    ({"": "abc/**\n"}, ["abc/z", "abc/x/y", "abcd/x"]),
    ({"": "*.log\n!keep.log\n"}, ["keep.log", "drop.log", "sub/keep.log"]),
    (
        {"": "file[0-9].txt\nname?.md\n"},
        ["file1.txt", "filex.txt", "name1.md", "name.md"],
    ),
    ({"": "\\#hash\n\\!bang\n# comment\n"}, ["#hash", "!bang", "comment"]),
    ({"": "trailing.txt   \n"}, ["trailing.txt"]),
    ({"": "*.txt\n", "sub": "!keep.txt\n"}, ["a.txt", "sub/keep.txt", "sub/other.txt"]),
    ({"sub": "*.md\n"}, ["a.md", "sub/a.md", "sub/deep/a.md"]),
    ({"sub": "/only.md\n"}, ["sub/only.md", "sub/deep/only.md"]),
    ({"": "foo\n"}, ["foo", "a/foo/", "b/foo"]),
    ({"": "foo/\n"}, ["foo", "a/foo/", "b/c/foo/"]),
    ({"": "*\n!*/\n!*.py\n"}, ["a.py", "b.txt", "sub/c.py", "sub/d.txt"]),
    ({"": "sub/\n!sub/keep.txt\n"}, ["sub/", "sub/keep.txt"]),
]

git = shutil.which("git")


def _git_ignored(repo: Path, paths: list[str]) -> set[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), "check-ignore", "--stdin"],
        input="\n".join(p.rstrip("/") for p in paths),
        capture_output=True,
        text=True,
        check=False,
    )
    return set(result.stdout.split())


def _engine_ignored(repo: Path, paths: list[str]) -> set[str]:
    engine = folder_engine(repo, TreeOptions(), hidden=True)
    ignored: set[str] = set()
    for path in paths:
        is_dir = path.endswith("/")
        clean = path.rstrip("/")
        parts = clean.split("/")
        # A path inside an ignored folder is ignored (the walk prunes it).
        reason = None
        for depth in range(1, len(parts)):
            reason = engine.check("/".join(parts[:depth]), is_dir=True)
            if reason:
                break
        reason = reason or engine.check(clean, is_dir=is_dir)
        if reason == IGNORE_FILE:
            ignored.add(clean)
    return ignored


@pytest.mark.skipif(git is None, reason="git not installed")
@pytest.mark.parametrize(("files", "paths"), GIT_CASES)
def test_gitignore_matches_git(tmp_path: Path, files: dict[str, str], paths: list[str]):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for folder, text in files.items():
        (tmp_path / folder).mkdir(parents=True, exist_ok=True)
        (tmp_path / folder / ".gitignore").write_text(text)
    for path in paths:
        target = tmp_path / path.rstrip("/")
        if path.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x")
    # git does not re-include a file inside an excluded folder; neither do we,
    # because the walk never descends into it. Compare only what git can see.
    expected = _git_ignored(tmp_path, paths)
    got = _engine_ignored(tmp_path, paths)
    for path in paths:
        clean = path.rstrip("/")
        parent_ignored = any(
            "/".join(clean.split("/")[:d]) in expected
            for d in range(1, clean.count("/") + 1)
        )
        if parent_ignored:
            continue
        assert (clean in got) == (clean in expected), (files, clean, expected, got)


class TestDefaults:
    @pytest.mark.parametrize(
        "path",
        [
            ".env",
            "config/.env.production",
            "keys/server.pem",
            "deploy/id_ed25519",
            "home/.aws/credentials",
            ".npmrc",
            "infra/terraform.tfstate",
            "client_secret_123.json",
        ],
    )
    def test_secrets(self, path):
        assert is_secret(path)
        assert IgnoreEngine().check(path, is_dir=False) == SECRET

    @pytest.mark.parametrize(
        "path", [".env.example", "env.py", "keys.md", "id_ed25519.pub", "README.md"]
    )
    def test_not_secrets(self, path):
        assert not is_secret(path)

    @pytest.mark.parametrize(
        ("path", "is_dir"),
        [
            ("node_modules", True),
            ("web/node_modules", True),
            ("pkg.egg-info", True),
            ("uv.lock", False),
            ("package-lock.json", False),
            ("app.min.js", False),
            ("mod.pyc", False),
            (".DS_Store", False),
        ],
    )
    def test_generated(self, path, is_dir):
        assert IgnoreEngine().check(path, is_dir=is_dir) == GENERATED

    @pytest.mark.parametrize("name", ["build", "bin", "vendor", "dist", "env", "out"])
    def test_ambiguous_names_are_kept(self, name):
        # Real code lives in folders with these names; .gitignore decides.
        assert IgnoreEngine().check(name, is_dir=True) is None

    def test_marker_folders(self, tmp_path: Path):
        (tmp_path / "myenv").mkdir()
        (tmp_path / "myenv" / "pyvenv.cfg").write_text("home = /usr")
        (tmp_path / "target").mkdir()
        (tmp_path / "target" / "CACHEDIR.TAG").write_bytes(
            b"Signature: 8a477f597d28d172789f06886806bc55\n"
        )
        (tmp_path / "fake").mkdir()
        (tmp_path / "fake" / "CACHEDIR.TAG").write_text("not the signature")
        engine = folder_engine(tmp_path, TreeOptions(), hidden=False)
        assert engine.check("myenv", is_dir=True) == GENERATED
        assert engine.check("target", is_dir=True) == GENERATED
        assert engine.check("fake", is_dir=True) is None

    def test_hidden_and_vcs(self):
        assert IgnoreEngine().check(".github", is_dir=True) == HIDDEN
        assert IgnoreEngine(hidden=True).check(".github", is_dir=True) is None
        assert IgnoreEngine(hidden=True).check(".git", is_dir=True) == VCS
        assert IgnoreEngine(defaults=False).check(".git", is_dir=True) == VCS


class TestIgnoreOption:
    def test_extra_patterns(self):
        engine = IgnoreEngine(extra=["tests/", "*.csv"])
        assert engine.check("tests", is_dir=True) == OPTION
        assert engine.check("data/x.csv", is_dir=False) == OPTION
        assert engine.check("src/x.py", is_dir=False) is None

    def test_negation_brings_back_a_default(self):
        engine = IgnoreEngine(extra=["!uv.lock", "!.env"])
        assert engine.check("uv.lock", is_dir=False) is None
        assert engine.check(".env", is_dir=False) is None

    def test_none_keeps_everything_but_vcs(self):
        engine = IgnoreEngine(defaults=False)
        for path in (".env", "node_modules", ".hidden"):
            assert engine.check(path, is_dir=path == "node_modules") is None


class TestParentIgnoreFiles:
    def test_repo_root_gitignore_applies_to_a_subfolder(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".gitignore").write_text("/src/generated/\n*.tmp\n")
        (tmp_path / ".git" / "info").mkdir()
        (tmp_path / ".git" / "info" / "exclude").write_text("secret_notes.md\n")
        src = tmp_path / "src"
        src.mkdir()
        engine = folder_engine(src, TreeOptions(), hidden=False)
        assert engine.check("generated", is_dir=True) == IGNORE_FILE
        assert engine.check("x.tmp", is_dir=False) == IGNORE_FILE
        assert engine.check("secret_notes.md", is_dir=False) == IGNORE_FILE
        assert engine.check("app.py", is_dir=False) is None

    def test_no_wandering_above_a_non_repo(self, tmp_path: Path):
        (tmp_path / ".gitignore").write_text("*.py\n")
        inner = tmp_path / "inner"
        inner.mkdir()
        engine = folder_engine(inner, TreeOptions(), hidden=False)
        assert engine.check("app.py", is_dir=False) is None
