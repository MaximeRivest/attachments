"""Repository facts for folder overviews: branch, commit, remote.

Read straight from the ``.git`` folder, never by running ``git``: a
repository's own configuration can make some git commands run programs
(``core.fsmonitor``, hooks), and attachments reads folders it did not
create — cloned repos, downloaded archives, shared drives.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


@dataclass
class GitInfo:
    root: Path  # the repository's working-tree root
    branch: str | None  # None when HEAD is detached
    commit: str | None  # full hash, None for a repository without commits
    remote: str | None  # origin's URL, credentials removed

    def summary(self) -> str:
        """One line, e.g. ``main @ 1a2b3c4d (github.com/o/r)``.

        Examples:
            >>> GitInfo(
            ...     Path("."), "main", "1a2b3c4d5e6f", "https://github.com/o/r"
            ... ).summary()
            'main @ 1a2b3c4d (https://github.com/o/r)'
            >>> GitInfo(Path("."), None, "1a2b3c4d5e6f", None).summary()
            'detached @ 1a2b3c4d'
        """
        head = self.branch or "detached"
        if self.commit:
            head += f" @ {self.commit[:8]}"
        else:
            head += " (no commits yet)"
        return f"{head} ({self.remote})" if self.remote else head


def find_repo_root(start: Path) -> Path | None:
    """The nearest folder at or above *start* that holds a ``.git``."""
    for folder in (start, *start.parents):
        try:
            if (folder / ".git").exists():
                return folder
        except OSError:  # an unreadable parent: stop looking
            return None
    return None


def _git_dir(root: Path) -> Path | None:
    dot_git = root / ".git"
    try:
        if dot_git.is_dir():
            return dot_git
    except OSError:
        return None
    try:  # worktrees and submodules: a file "gitdir: <path>"
        text = dot_git.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if text.startswith("gitdir:"):
        target = Path(text[len("gitdir:") :].strip())
        return target if target.is_absolute() else (root / target).resolve()
    return None


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _resolve_ref(git_dir: Path, common: Path, ref: str) -> str | None:
    for base in (git_dir, common):
        text = _read(base / ref)
        if text and re.fullmatch(r"[0-9a-f]{40,64}", text.strip()):
            return text.strip()
    packed = _read(common / "packed-refs") or ""
    for line in packed.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == ref:
            return parts[0]
    return None


def strip_credentials(url: str) -> str:
    """Remove ``user:token@`` from a URL (remote URLs often embed tokens).

    Examples:
        >>> strip_credentials("https://bot:ghp_secret@github.com/o/r.git")
        'https://github.com/o/r.git'
        >>> strip_credentials("git@github.com:o/r.git")
        'git@github.com:o/r.git'
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if parts.scheme and parts.username is not None:
        host = parts.hostname or ""
        if parts.port:
            host += f":{parts.port}"
        return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
    return url


def _origin_url(config: str) -> str | None:
    section = None
    for raw in config.splitlines():
        line = raw.strip()
        if line.startswith("["):
            section = line
            continue
        if section and re.fullmatch(r'\[remote\s+"origin"\]', section):
            key, _, value = line.partition("=")
            if key.strip().lower() == "url" and value.strip():
                return strip_credentials(value.strip())
    return None


def read_git_info(root: Path) -> GitInfo | None:
    """Branch, commit and origin of the repository at *root*, if any."""
    git_dir = _git_dir(root)
    if git_dir is None:
        return None
    common_text = _read(git_dir / "commondir")
    common = (git_dir / common_text.strip()).resolve() if common_text else git_dir
    head = (_read(git_dir / "HEAD") or "").strip()
    branch: str | None = None
    commit: str | None = None
    if head.startswith("ref:"):
        ref = head[len("ref:") :].strip()
        branch = ref.removeprefix("refs/heads/")
        commit = _resolve_ref(git_dir, common, ref)
    elif re.fullmatch(r"[0-9a-f]{40,64}", head):
        commit = head
    remote = _origin_url(_read(common / "config") or "")
    return GitInfo(root, branch, commit, remote)
