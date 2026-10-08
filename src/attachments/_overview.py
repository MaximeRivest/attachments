"""The overview artifact of a folder, repository, pattern or archive.

Built from a ``TreeReport`` (``_sources/local.py``): a header (what this
is, how many files and bytes were read, the git branch and commit), what
was skipped and why, any limit that stopped reading, then the file tree.
Its ``meta.kind`` is ``"directory"``; the numbers are in ``meta.extra``.

Shown by default for folders and repositories (``tree: auto``): a model
reading a project is helped by its layout, as repomix and gitingest
found. For patterns and archives only when something must be said (a
limit was hit, nothing was read, an option was invalid).
"""

from __future__ import annotations

from typing import Any

from ._sources import _ignore
from ._sources.local import (
    GLOB_OPTION,
    NOT_RECURSIVE,
    SPECIAL,
    SYMLINK,
    UNREADABLE,
    TreeReport,
)
from .types import make_artifact

#: How each skip reason is named in the overview, and how to get it back.
_REASONS: dict[str, tuple[str, str]] = {
    _ignore.SECRET: ("secrets", "add [ignore: none] to include"),
    _ignore.GENERATED: (
        "dependencies and generated files",
        'add [ignore: "!name"] to include one',
    ),
    _ignore.HIDDEN: ("hidden", "add [hidden: true] to include"),
    _ignore.IGNORE_FILE: (
        ".gitignore / .attachmentsignore",
        'add [ignore: "!name"] to include one',
    ),
    _ignore.OPTION: ("your ignore patterns", ""),
    SYMLINK: ("links leading outside the folder", "never followed"),
    SPECIAL: ("not regular files", ""),
    UNREADABLE: ("unreadable", ""),
    NOT_RECURSIVE: ("subfolders", "recursive: false"),
    GLOB_OPTION: ("not matching glob", ""),
}

_KIND_WORDS = {
    "folder": "Folder",
    "repo": "Repository",
    "pattern": "Files matching",
    "archive": "Archive",
}


def human_size(size: int) -> str:
    """``1234567`` -> ``'1.2 MB'`` (powers of 1000, like ``max_size: 50MB``).

    Examples:
        >>> human_size(999), human_size(48_200), human_size(3_400_000)
        ('999 B', '48.2 KB', '3.4 MB')
    """
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1000 or unit == "GB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1000
    return f"{size} B"  # pragma: no cover


def _count(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def render_tree(root: str, paths: list[tuple[str, str]]) -> str:
    """A ``tree``-style listing of ``(path, annotation)`` pairs, in order.

    Examples:
        >>> print(
        ...     render_tree(
        ...         "proj",
        ...         [
        ...             ("README.md", ""),
        ...             ("src/a.py", ""),
        ...             ("src/lib/b.py", ""),
        ...             ("data.zip", "3 files"),
        ...         ],
        ...     )
        ... )
        proj/
        ├── README.md
        ├── src/
        │   ├── a.py
        │   └── lib/
        │       └── b.py
        └── data.zip  (3 files)
    """
    tree: dict[str, Any] = {}
    for path, note in paths:
        node = tree
        parts = path.split("/")
        for part in parts[:-1]:
            node = node.setdefault(part + "/", {})
        node[parts[-1]] = note
    lines = [root.rstrip("/") + "/"]

    def walk(node: dict[str, Any], prefix: str) -> None:
        items = list(node.items())
        for i, (name, child) in enumerate(items):
            last = i == len(items) - 1
            branch = "└── " if last else "├── "
            if isinstance(child, dict):
                lines.append(prefix + branch + name)
                walk(child, prefix + ("    " if last else "│   "))
            else:
                lines.append(prefix + branch + name + (f"  ({child})" if child else ""))

    walk(tree, "")
    return "\n".join(lines)


def _skipped_lines(report: TreeReport) -> list[str]:
    lines: list[str] = []
    for reason, skipped in report.skipped.items():
        if reason == _ignore.VCS:
            continue  # .git is never content; saying so is noise
        name, remedy = _REASONS.get(reason, (reason, ""))
        parts = []
        if skipped.folders:
            parts.append(_count(skipped.folders, "folder"))
        if skipped.files:
            parts.append(_count(skipped.files, "file"))
        total = skipped.files + skipped.folders
        examples = ", ".join(skipped.examples)
        if total > len(skipped.examples):
            examples += ", …"
        line = f"- {name}: {' and '.join(parts)} ({examples})"
        if remedy:
            line += f" — {remedy}"
        lines.append(line)
    return lines


def _limit_line(report: TreeReport) -> str | None:
    if report.scan_capped:
        from ._sources.local import MAX_SCAN_ENTRIES

        return (
            f"Stopped looking after {MAX_SCAN_ENTRIES:,} entries: the folder is "
            "larger than that. Point at a subfolder or use a pattern."
        )
    if report.limit is None:
        return None
    value = getattr(report.options, report.limit)
    shown = human_size(value) if report.limit == "max_size" else f"{value:,}"
    return (
        f"Stopped at {report.limit}: {shown} — {_count(report.not_read, 'more file')} "
        f"not read. Raise it with [{report.limit}: ...] (0 = no limit)."
    )


def wants_tree(report: TreeReport) -> bool:
    """Whether the overview shows the file tree (``tree`` option, ``files``)."""
    if not report.options.files:
        return True  # files: false asks for exactly this
    if report.options.tree == "auto":
        return report.kind in ("folder", "repo")
    return bool(report.options.tree)


def needs_overview(report: TreeReport) -> bool:
    """Whether to emit the overview at all."""
    return (
        wants_tree(report)
        or report.limit is not None
        or report.scan_capped
        or bool(report.warnings)
        or (report.files_read == 0 and bool(report.skipped))
    )


def overview_artifact(report: TreeReport) -> dict[str, Any]:
    """The ``kind: directory`` artifact describing *report*."""
    count = report.files_read
    header = f"{_KIND_WORDS.get(report.kind, 'Folder')} {report.label}"
    if report.options.files:
        header += f" — {_count(count, 'file')} read, {human_size(report.total_bytes)}"
    else:
        header += (
            f" — {_count(count, 'file')}, {human_size(report.total_bytes)} "
            "(contents not read: files: false)"
        )
    lines = [header]
    if report.git is not None:
        lines.append(f"Git: {report.git.summary()}")
    limit = _limit_line(report)
    if limit:
        lines.append(limit)
    skipped = _skipped_lines(report)
    if skipped:
        lines.append("Skipped:")
        lines.extend(skipped)
    if wants_tree(report):
        entries = [
            (e.path, _count(e.members, "file") if e.members is not None else "")
            for e in report.entries
        ]
        lines.append("")
        lines.append(
            render_tree(report.root_name, entries) if entries else "(no files)"
        )

    warnings = list(report.warnings)
    if limit:
        warnings.append(limit)

    extra: dict[str, Any] = {
        "kind": report.kind,
        "root": report.root_name,
        "files": count,
        "bytes": report.total_bytes,
        "skipped": {
            reason: {"files": s.files, "folders": s.folders, "examples": s.examples}
            for reason, s in report.skipped.items()
        },
    }
    if report.limit:
        extra["limit"] = report.limit
        extra["not_read"] = report.not_read
    if report.scan_capped:
        extra["scan_capped"] = True
    if report.git is not None:
        extra["git"] = {
            "branch": report.git.branch,
            "commit": report.git.commit,
            "remote": report.git.remote,
        }
    meta: dict[str, Any] = {"source": report.label, "kind": "directory", "extra": extra}
    if warnings:
        meta["warnings"] = warnings
    return make_artifact(text="\n".join(lines), meta=meta)
