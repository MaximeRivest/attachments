"""GitHub sources: ``github://owner/repo`` and github.com repo roots.

Handles shallow-cloning a GitHub repository (repo root ONLY — deeper
github.com URLs fall through to the plain HTTP download path) into a
temp directory that ``unpack()`` then walks like any local directory.
Registers the ``github://`` source option schema (``ref``) at import
time, exactly like processors register theirs.

Contributor note: to add a new source, add one module in this package,
register it at import time (plus an import line in the block at the
BOTTOM of ``__init__.py`` — top-of-file imports run before the registry
exists and circular-import), and add tests — see DEVELOPMENT.md
("Building New Sources").
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from .._options import Option, register_options, snapshot_option_defaults

_GITHUB_OWNER_REPO_RE = re.compile(
    r"^[a-zA-Z0-9][-a-zA-Z0-9_.]*[a-zA-Z0-9]?/[a-zA-Z0-9][-a-zA-Z0-9_.]*[a-zA-Z0-9]?(\.git)?$"
)

# Declared option schema for the built-in github:// source. The resolved
# `ref` is consumed by core._apply_source_options into a ?ref=... query
# parameter, which _clone_github_to_temp reads below.
register_options(
    "github://",
    (
        Option(
            "ref",
            "str",
            aliases=("branch", "tag"),
            help="Git branch, tag, or ref to clone.",
            example="ref: main",
        ),
    ),
)
snapshot_option_defaults()


def _validate_github_owner_repo(owner_repo: str) -> None:
    """Validate owner/repo format to prevent command injection."""
    # Must be exactly owner/repo format with safe characters
    if not _GITHUB_OWNER_REPO_RE.match(owner_repo):
        raise ValueError(f"Invalid GitHub owner/repo format: {owner_repo}")
    # Additional safety: no shell metacharacters or git options
    dangerous_patterns = ["--", "..", ";", "|", "&", "$", "`", "\n", "\r"]
    for pattern in dangerous_patterns:
        if pattern in owner_repo:
            raise ValueError(f"Invalid characters in GitHub spec: {owner_repo}")


def _clone_github_to_temp(spec: str) -> Path:
    """Clone a GitHub repository into a temporary directory.
    Supported forms:
      - github://owner/repo[?ref=branch_or_tag]
      - https://github.com/owner/repo[.git][?ref=...]
    Requires the `git` CLI to be available in PATH.

    Returns the path to the temporary directory.
    """
    import urllib.parse

    def parse(spec: str):
        if spec.startswith("github://"):
            rest = spec[len("github://") :]
            if "?" in rest:
                repo_path, qs = rest.split("?", 1)
                qs_dict = dict(urllib.parse.parse_qsl(qs))
            else:
                repo_path, qs_dict = rest, {}
            owner_repo = repo_path.strip("/")
            _validate_github_owner_repo(owner_repo)
            url = f"https://github.com/{owner_repo}.git"
            ref = qs_dict.get("ref")
            return url, ref
        if spec.startswith("https://github.com/"):
            u = urllib.parse.urlparse(spec)
            parts = [p for p in u.path.split("/") if p]
            # Only treat EXACT repo roots as cloneable: /owner/repo or /owner/repo.git
            if len(parts) != 2:
                raise ValueError("Unsupported GitHub spec")
            owner, repo = parts
            owner_repo = f"{owner}/{repo}"
            _validate_github_owner_repo(owner_repo)
            if not repo.endswith(".git"):
                repo = repo + ".git"
            ref = dict(urllib.parse.parse_qsl(u.query or "")).get("ref")
            url = f"https://github.com/{owner}/{repo}"
            return url, ref
        raise ValueError("Unsupported GitHub spec")

    url, ref = parse(spec)
    tmpdir = Path(tempfile.mkdtemp(prefix="attachments_github_"))
    # Shallow clone
    cmd = ["git", "clone", "--depth", "1"]
    if ref:
        cmd += ["--branch", ref]
    cmd += [url, str(tmpdir)]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except Exception as e:
        raise RuntimeError(f"git clone failed: {e}") from e

    return tmpdir


# --- Added for HTTP(S) support ---
def _is_github_repo_root_url(url: str) -> bool:
    """Return True if URL is exactly a GitHub repo root.

    Matches: owner/repo, owner/repo.git, with optional ?ref=...

    Examples:
        >>> _is_github_repo_root_url("https://github.com/owner/repo")
        True
        >>> _is_github_repo_root_url("https://github.com/owner/repo.git")
        True
        >>> _is_github_repo_root_url("https://github.com/owner/repo?ref=main")
        True
        >>> _is_github_repo_root_url("https://github.com/owner/repo/blob/main/file.py")
        False
        >>> _is_github_repo_root_url("https://example.com/owner/repo")
        False
    """
    if not url.startswith("https://github.com/"):
        return False
    from urllib.parse import urlparse

    parts = [p for p in urlparse(url).path.split("/") if p]
    return len(parts) == 2  # /owner/repo or /owner/repo.git
