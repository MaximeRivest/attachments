"""Repository facts read from ``.git`` without running git (``_git.py``)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from attachments._sources._git import find_repo_root, read_git_info

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git missing")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=t", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "trunk")
    (tmp_path / "a.txt").write_text("a")
    git(tmp_path, "add", "a.txt")
    git(tmp_path, "commit", "-qm", "one")
    return tmp_path


def test_branch_and_commit(repo: Path):
    info = read_git_info(repo)
    assert info.branch == "trunk"
    assert info.commit == git(repo, "rev-parse", "HEAD")


def test_packed_refs(repo: Path):
    git(repo, "pack-refs", "--all")
    assert not (repo / ".git" / "refs" / "heads" / "trunk").exists()
    assert read_git_info(repo).commit == git(repo, "rev-parse", "HEAD")


def test_detached_head(repo: Path):
    git(repo, "checkout", "-q", "--detach")
    info = read_git_info(repo)
    assert info.branch is None and info.summary().startswith("detached @ ")


def test_worktree(repo: Path, tmp_path_factory):
    other = tmp_path_factory.mktemp("wt") / "feature"
    git(repo, "worktree", "add", "-q", "-b", "feature", str(other))
    info = read_git_info(other)
    assert info.branch == "feature"
    assert info.commit == git(repo, "rev-parse", "HEAD")


def test_no_commits_yet(tmp_path: Path):
    git(tmp_path, "init", "-q", "-b", "main")
    assert read_git_info(tmp_path).summary() == "main (no commits yet)"


def test_repo_root_from_a_subfolder(repo: Path):
    (repo / "deep" / "er").mkdir(parents=True)
    assert find_repo_root(repo / "deep" / "er") == repo
