"""Local filesystem sources: single files, glob patterns, directory walks.

Handles recursive directory walks — deterministic (sorted) order, with
VCS/cache directories pruned and a top-level ``.gitignore`` applied via a
documented fnmatch subset — expanding nested raw archives by extension
via ``archives.py``. Single local files are read in the ``unpack()``
dispatch itself (see ``__init__.py``); glob patterns are expanded here
by ``_expand_glob``.

Contributor note: to add a new source, add one module in this package,
register it at import time (plus an import line in the block at the
BOTTOM of ``__init__.py`` — top-of-file imports run before the registry
exists and circular-import), and add tests — see DEVELOPMENT.md
("Building New Sources").
"""

from __future__ import annotations

import fnmatch
import glob
import os
from pathlib import Path

from .archives import _explode_archive_bytes, _is_raw_archive_name

# Glob metacharacters checked in the LAST path component (see _looks_like_glob).
_GLOB_CHARS = "*?["


def _looks_like_glob(s: str) -> bool:
    """Return True when ``s`` should be treated as a glob pattern.

    The spec'd rule: True when ``"**"`` appears anywhere in the string, or
    when the component AFTER the last path separator contains any of
    ``* ? [``.

    Known limitation (documented, by design): a pattern like
    ``src/*/file.txt`` — wildcard only in a MIDDLE component, no ``**`` —
    is NOT detected as a glob.

    Examples:
        >>> _looks_like_glob("docs/*.txt")
        True
        >>> _looks_like_glob("src/**/x.py")
        True
        >>> _looks_like_glob("file[1].txt")
        True
        >>> _looks_like_glob("plain/file.txt")
        False
        >>> _looks_like_glob("src/*/file.txt")  # known limitation
        False
    """
    if "**" in s:
        return True
    last = s.replace(os.sep, "/").rsplit("/", 1)[-1]
    return any(c in last for c in _GLOB_CHARS)


def _no_match_message(pattern: str) -> str:
    """Error message for a glob with zero matches, with a DSL hint when apt.

    A bracket group that fails the DSL grammar (e.g. an unquoted comma in a
    value: ``page.html[select: h1,p]``) is left in the source by
    ``parse_dsl`` and then routed here because ``[`` is a glob
    metacharacter. When the text BEFORE the final ``[...]`` group names an
    existing file, the real problem is the malformed options block, not the
    glob — say so instead of the misleading "matched no files".
    """
    msg = f"Glob pattern matched no files: {pattern}"
    if pattern.endswith("]"):
        depth = 0
        for i in range(len(pattern) - 1, -1, -1):
            if pattern[i] == "]":
                depth += 1
            elif pattern[i] == "[":
                depth -= 1
                if depth == 0:
                    base = pattern[:i].strip()
                    if base and os.path.isfile(base) and ":" in pattern[i:]:
                        return (
                            f"{msg} — but {base!r} exists. The trailing "
                            f"{pattern[i:]!r} is not a valid DSL options block "
                            "(every comma-separated segment needs 'key: value'; "
                            'quote values containing commas, e.g. [select: "h1, p"]), '
                            "so it was treated as part of the path."
                        )
                    break
    return msg


def _glob_static_base(pattern: str) -> str:
    """Static base of a glob pattern: the leading glob-free components.

    Mirrors v1's ``get_glob_base_path`` rule. Returns ``""`` when there is
    no static base (pattern starts with a glob component).
    """
    norm = pattern.replace(os.sep, "/")
    parts = norm.split("/")
    static: list[str] = []
    for part in parts[:-1]:  # last component is the filename pattern
        if any(c in part for c in _GLOB_CHARS):
            break
        static.append(part)
    return "/".join(static)


def _expand_glob(pattern: str) -> list[tuple[str, bytes]]:
    """Expand a glob pattern into ``(name, bytes)`` pairs.

    - ``glob.glob(pattern, recursive=True)``; regular files only; sorted
      for determinism.
    - Zero matches raise ``ValueError`` (core converts it to an
      unpack-error artifact, same as a non-existent input).
    - Result names are relative to the pattern's static base (the leading
      glob-free components — v1's ``get_glob_base_path`` rule); when there
      is no static base, the matched path is used as given.
    - Archives matched by the glob are expanded by extension, like the
      single-file path.

    v1 parity notes:
    - Ignore patterns are deliberately NOT applied to glob results — a
      glob is explicit user intent (matches v1).
    - Stdlib ``glob`` skips dotfiles unless the pattern names them.

    DIVERGENCE from v1: no unconditional binary-skipping in glob mode —
    v3 has real processors for binary formats (pdf/xlsx/images); v1 only
    skipped them because everything fed a text pipeline.
    """
    matches = sorted(m for m in glob.glob(pattern, recursive=True) if os.path.isfile(m))
    if not matches:
        raise ValueError(_no_match_message(pattern))
    base = _glob_static_base(pattern)
    out: list[tuple[str, bytes]] = []
    for m in matches:
        try:
            with open(m, "rb") as f:
                data = f.read()
        except Exception:
            continue
        name = os.path.relpath(m, base).replace(os.sep, "/") if base else m
        if _is_raw_archive_name(name):
            out.extend(_explode_archive_bytes(name, data))
        else:
            out.append((name, data))
    return out


def _parse_root_gitignore(root: Path) -> list[tuple[str, bool, bool]]:
    """Parse ``root/.gitignore`` into ``(pattern, is_dir, anchored)`` tuples.

    Documented stdlib-fnmatch SUBSET of gitignore semantics:

    - Top-level ``.gitignore`` only (nested ones are ignored).
    - ``#`` comments and blank lines are stripped.
    - ``!`` negation is unsupported — such lines are skipped entirely.
    - A trailing ``/`` marks a directory pattern (prunes ``dirnames``
      in-place before descent).
    - A leading ``/`` is stripped and the pattern anchors to the root
      (matched against the root-relative path only, not the basename).
    - Patterns are matched with ``fnmatch`` against the root-relative
      path AND the basename; no special ``**`` handling beyond fnmatch's
      ``*`` (which matches across ``/``).

    The ``.gitignore`` file itself stays in the output unless a pattern
    excludes it.
    """
    gi = root / ".gitignore"
    patterns: list[tuple[str, bool, bool]] = []
    try:
        text = gi.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return patterns
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        is_dir = line.endswith("/")
        if is_dir:
            line = line.rstrip("/")
        anchored = line.startswith("/")
        if anchored:
            line = line.lstrip("/")
        if line:
            patterns.append((line, is_dir, anchored))
    return patterns


def _gitignore_match(
    rel: str,
    name: str,
    patterns: list[tuple[str, bool, bool]],
    *,
    is_dir: bool = False,
) -> bool:
    """True when ``rel`` (root-relative path) / ``name`` (basename) matches.

    Directory patterns (trailing ``/``) only apply when ``is_dir=True``;
    file patterns apply to both files and directories. Anchored patterns
    (leading ``/``) match the root-relative path only.
    """
    for pat, pat_is_dir, anchored in patterns:
        if pat_is_dir and not is_dir:
            continue
        if fnmatch.fnmatch(rel, pat):
            return True
        if not anchored and fnmatch.fnmatch(name, pat):
            return True
    return False


def _walk_directory(path: Path) -> list[tuple[str, bytes]]:
    """Return ``(relative_path, bytes)`` for all files in a directory.

    Skips common VCS/cache directories like ``.git/`` by default. When
    (and only when) a ``.gitignore`` exists at the walk ROOT, its
    patterns are applied using the documented fnmatch subset (see
    ``_parse_root_gitignore``); the hard prune set
    ``{.git, .hg, .svn, __pycache__}`` always applies, gitignore or not.
    Filtering happens inside the existing sorted walk, so determinism is
    untouched, and a directory with no ``.gitignore`` behaves exactly as
    before. Bonus: the ``github://`` source clones then calls this
    helper, so cloned repos get gitignore-aware walks automatically.

    The walk is deterministic: directories and filenames are visited in
    sorted order, so artifact order — and therefore ``.text``, ``.chunk()``
    and the repr — never depends on filesystem internals or file-creation
    history (raw ``os.walk`` order varies across filesystems/machines,
    which would break prompt caching and reproducibility).
    """
    root = path.resolve()
    ignore_patterns = _parse_root_gitignore(root)
    out: list[tuple[str, bytes]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip common VCS and cache directories
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            rel_dir = ""
        # Prune directories we don't want to descend into
        for d in list(dirnames):
            if d in {".git", ".hg", ".svn", "__pycache__"}:
                dirnames.remove(d)
                continue
            if ignore_patterns:
                rel_d = os.path.join(rel_dir, d) if rel_dir else d
                if _gitignore_match(rel_d, d, ignore_patterns, is_dir=True):
                    dirnames.remove(d)
        # Sort in place so os.walk descends in deterministic order.
        dirnames.sort()

        for fn in sorted(filenames):
            if ignore_patterns:
                rel_f = os.path.join(rel_dir, fn) if rel_dir else fn
                if _gitignore_match(rel_f, fn, ignore_patterns):
                    continue
            fpath = Path(dirpath) / fn
            try:
                with open(fpath, "rb") as f:
                    data = f.read()
            except Exception:
                continue
            rel = os.path.join(rel_dir, fn) if rel_dir else fn
            # Expand nested archives in-place (by extension only)
            if _is_raw_archive_name(rel):
                out.extend(_explode_archive_bytes(rel, data))
            else:
                out.append((rel, data))
    return out
