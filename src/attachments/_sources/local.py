"""Local trees of files: folders, wildcard patterns, archives, cloned repos.

Every tree is read the same way, in two steps:

1. **List**: walk the tree in sorted order (deterministic on every
   filesystem), asking the skip engine (``_ignore.py``) about each folder
   and file. Nothing is read yet.
2. **Read**: take files in that order until ``max_files`` or ``max_size``
   is reached — a file too big for what is left of the size budget is
   skipped and the next one tried. Archives are expanded, and their
   members go through the same skip rules and limits.

Everything skipped is counted by reason in a ``TreeReport``, which core
turns into the folder overview (the tree, git details, what was left out).
``files: false`` stops after step 1: the overview without the contents.

Safety: symbolic links that lead outside the tree are not followed (a
cloned repository can contain a link to ``~/.ssh/id_rsa``), and only
regular files are read (a named pipe would block forever). Scanning stops
after ``MAX_SCAN_ENTRIES`` entries, so ``att("/")`` returns instead of
walking a whole disk.
"""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .._options import Option, register_options, snapshot_option_defaults
from ._file import SourceFile
from ._git import GitInfo, find_repo_root, read_git_info
from ._guards import MAX_HTTP_DOWNLOAD_BYTES
from ._ignore import (
    CACHEDIR_SIGNATURE,
    IGNORE_FILES,
    IgnoreEngine,
    compile_rules,
    split_patterns,
)

#: Default ``max_files``: files read from one folder, pattern or archive.
DEFAULT_MAX_FILES = 1000
#: Default ``max_size``: total bytes read (the same cap as one download).
DEFAULT_MAX_SIZE = MAX_HTTP_DOWNLOAD_BYTES
#: Entries (files and folders) examined before a scan gives up.
MAX_SCAN_ENTRIES = int(os.environ.get("ATT_MAX_SCAN_ENTRIES", "200000"))
#: Largest ignore file read (bigger ones are not ignore files).
_MAX_IGNORE_FILE = 1024 * 1024
#: Example paths kept per skip reason.
_EXAMPLES = 5

#: Extra skip reasons (besides the engine's).
SYMLINK = "link outside the folder"
SPECIAL = "not a regular file"
UNREADABLE = "unreadable"
NOT_RECURSIVE = "subfolder (recursive: false)"
GLOB_OPTION = "not matching glob"


class InvalidSourceOption(ValueError):
    """A folder option has a value that cannot be used."""


def _size_label(size: int) -> str:
    for unit, factor in (("GiB", 2**30), ("MiB", 2**20), ("KiB", 2**10)):
        if size % factor == 0:
            return f"{size // factor}{unit}"
    return str(size)


#: Folder options: local folders, patterns and archives (``file://``) and
#: GitHub repositories share them.
TREE_OPTIONS = (
    Option(
        "files",
        "bool",
        default=True,
        help="Read the files (false: only the overview of what is there)",
        example="files: false",
    ),
    Option(
        "tree",
        "bool_or_auto",
        default="auto",
        help=(
            "Start with an overview: file tree, git branch and commit, what was "
            "skipped (auto: on for folders and repos, off for patterns and archives)"
        ),
        example="tree: false",
    ),
    Option(
        "ignore",
        "str",
        help=(
            "More to skip, .gitignore syntax, comma-separated; !pattern brings back "
            "a skipped file; none skips nothing but .git"
        ),
        example='ignore: "tests/, *.csv"',
    ),
    Option(
        "hidden",
        "bool",
        default=False,
        help="Include hidden files and folders (names starting with a dot)",
        example="hidden: true",
    ),
    Option(
        "glob",
        "str",
        aliases=("include",),
        help="Only files matching these patterns (.gitignore syntax, comma-separated)",
        example='glob: "*.py, *.md"',
    ),
    Option(
        "recursive",
        "bool",
        default=True,
        help="Read subfolders too",
        example="recursive: false",
    ),
    Option(
        "max_files",
        "int",
        default=DEFAULT_MAX_FILES,
        help="Most files read (0 = no limit)",
        example="max_files: 200",
    ),
    Option(
        "max_size",
        "str_or_int",
        default=_size_label(DEFAULT_MAX_SIZE),
        help="Most bytes read in total, e.g. 50MB (0 = no limit)",
        example="max_size: 50MB",
    ),
)

register_options("file://", TREE_OPTIONS)
snapshot_option_defaults()


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------

_SIZE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kmgt]?i?b?)?\s*$", re.IGNORECASE)


def parse_size(value: Any) -> int:
    """Bytes from an int or a string like ``"50MB"``, ``"1.5 GiB"``, ``"500k"``.

    KB/MB/GB are powers of 1000, KiB/MiB/GiB powers of 1024.

    Examples:
        >>> parse_size(1024), parse_size("50MB"), parse_size("2 MiB"), parse_size("0")
        (1024, 50000000, 2097152, 0)
        >>> parse_size("lots")
        Traceback (most recent call last):
        ...
        attachments._sources.local.InvalidSourceOption: max_size must be ...
    """
    if isinstance(value, bool):
        raise InvalidSourceOption(_SIZE_HELP + f", got {value!r}")
    if isinstance(value, int):
        if value < 0:
            raise InvalidSourceOption(_SIZE_HELP + f", got {value!r}")
        return value
    match = _SIZE.match(str(value))
    if not match:
        raise InvalidSourceOption(_SIZE_HELP + f", got {value!r}")
    number, unit = float(match.group(1)), (match.group(2) or "").lower()
    base = 1024 if "i" in unit else 1000
    power = {"": 0, "k": 1, "m": 2, "g": 3, "t": 4}[
        unit[:1] if unit[:1] in "kmgt" else ""
    ]
    return int(number * base**power)


_SIZE_HELP = (
    "max_size must be a size like 50MB, 1.5GiB or a number of bytes (0 = no limit)"
)

#: ``ignore`` words from attachments 0.25, mapped to today's behaviour.
_DEFAULT_WORDS = {"standard", "auto", "default", "gitignore", "attachmentsignore"}
_NONE_WORDS = {"none", "raw", "all"}


@dataclass(frozen=True)
class TreeOptions:
    """Resolved folder options (see the ``file://`` option schema)."""

    files: bool = True
    tree: bool | str = "auto"
    recursive: bool = True
    hidden: bool = False
    defaults: bool = True
    ignore: tuple[str, ...] = ()
    glob: tuple[str, ...] = ()
    max_files: int = DEFAULT_MAX_FILES
    max_size: int = DEFAULT_MAX_SIZE

    @classmethod
    def from_options(
        cls, options: dict[str, Any] | None
    ) -> tuple[TreeOptions, list[str]]:
        """Validate resolved option values; returns ``(options, warnings)``.

        Examples:
            >>> o, w = TreeOptions.from_options(
            ...     {"ignore": "none, *.log", "max_files": 0}
            ... )
            >>> o.defaults, o.ignore, o.max_files, w
            (False, ('*.log',), 0, [])
            >>> print(TreeOptions.from_options({"ignore": "minimal"})[1][0])
            ignore: 'minimal' (from attachments 0.25) is not supported; ...
        """
        options = dict(options or {})
        warnings: list[str] = []
        defaults = True
        patterns: list[str] = []
        for pattern in split_patterns(options.get("ignore")):
            word = pattern.lower()
            if word in _NONE_WORDS:
                defaults = False
            elif word in _DEFAULT_WORDS:
                continue
            elif word == "minimal":
                warnings.append(
                    "ignore: 'minimal' (from attachments 0.25) is not supported; "
                    "the default rules apply"
                )
            else:
                patterns.append(pattern)
        max_files = options.get("max_files", DEFAULT_MAX_FILES)
        if (
            isinstance(max_files, bool)
            or not isinstance(max_files, int)
            or max_files < 0
        ):
            raise InvalidSourceOption(
                f"max_files must be an integer >= 0 (0 = no limit), got {max_files!r}"
            )
        max_size = parse_size(options.get("max_size", DEFAULT_MAX_SIZE))
        tree = options.get("tree", "auto")
        if isinstance(tree, str) and tree.lower() == "always":
            tree = True
        if tree not in (True, False) and str(tree).lower() != "auto":
            raise InvalidSourceOption(f"tree must be true, false or auto, got {tree!r}")
        return (
            cls(
                files=bool(options.get("files", True)),
                tree=tree if isinstance(tree, bool) else "auto",
                recursive=bool(options.get("recursive", True)),
                hidden=bool(options.get("hidden", False)),
                defaults=defaults,
                ignore=tuple(patterns),
                glob=tuple(split_patterns(options.get("glob"))),
                max_files=max_files,
                max_size=max_size,
            ),
            warnings,
        )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass
class Skipped:
    files: int = 0
    folders: int = 0
    examples: list[str] = field(default_factory=list)

    def add(self, path: str, *, folder: bool) -> None:
        if folder:
            self.folders += 1
        else:
            self.files += 1
        if len(self.examples) < _EXAMPLES:
            self.examples.append(path + ("/" if folder else ""))


@dataclass
class Entry:
    path: str  # relative to the tree's root, "/"-separated
    size: int
    members: int | None = None  # archives: members kept


@dataclass
class TreeReport:
    """What a tree contained, what was read, and what was left out."""

    label: str  # the input as given ("docs/", "src/**/*.py", "github://o/r")
    kind: str  # "folder" | "pattern" | "repo" | "archive"
    root_name: str  # shown at the top of the tree
    options: TreeOptions
    entries: list[Entry] = field(default_factory=list)
    skipped: dict[str, Skipped] = field(default_factory=dict)
    limit: str | None = None  # "max_files" or "max_size", the first hit
    not_read: int = 0  # files left out by the limits
    scan_capped: bool = False  # stopped after MAX_SCAN_ENTRIES
    git: GitInfo | None = None
    warnings: list[str] = field(default_factory=list)

    def skip(self, reason: str, path: str, *, folder: bool = False) -> None:
        self.skipped.setdefault(reason, Skipped()).add(path, folder=folder)

    @property
    def total_bytes(self) -> int:
        return sum(e.size for e in self.entries)

    @property
    def files_read(self) -> int:
        return sum(e.members if e.members is not None else 1 for e in self.entries)


# ---------------------------------------------------------------------------
# Engines for real folders and for archive members
# ---------------------------------------------------------------------------


def _read_small(path: Path) -> str | None:
    try:
        if not path.is_file() or path.stat().st_size > _MAX_IGNORE_FILE:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _is_cachedir_tag(data: bytes | None) -> bool:
    return data is not None and data.startswith(CACHEDIR_SIGNATURE)


def folder_engine(root: Path, opts: TreeOptions, *, hidden: bool) -> IgnoreEngine:
    """Skip engine for a folder on disk, with parent ignore files applied."""

    def load(folder: str, name: str) -> str | None:
        return _read_small(root / folder / name)

    def marked(folder: str) -> bool:
        base = root / folder
        try:  # unreadable folders raise PermissionError, not False
            if (base / "pyvenv.cfg").is_file():
                return True
            with open(base / "CACHEDIR.TAG", "rb") as fh:
                return _is_cachedir_tag(fh.read(len(CACHEDIR_SIGNATURE)))
        except OSError:
            return False

    outer = []
    if opts.defaults:
        repo = find_repo_root(root)
        if repo is not None:
            # Parent folders' ignore files, closest first, then info/exclude.
            folder = root
            while folder != repo:
                folder = folder.parent
                prefix = root.relative_to(folder).as_posix() + "/"
                for name in reversed(IGNORE_FILES):
                    text = _read_small(folder / name)
                    if text:
                        outer.append((prefix, compile_rules(text.splitlines())))
            prefix = "" if repo == root else root.relative_to(repo).as_posix() + "/"
            exclude = _read_small(repo / ".git" / "info" / "exclude")
            if exclude:
                outer.append((prefix, compile_rules(exclude.splitlines())))
    return IgnoreEngine(
        extra=list(opts.ignore),
        defaults=opts.defaults,
        hidden=hidden,
        load=load,
        marked=marked,
        outer=outer,
    )


def member_engine(members: dict[str, bytes], opts: TreeOptions) -> IgnoreEngine:
    """Skip engine for archive members (ignore files read from the archive)."""

    def load(folder: str, name: str) -> str | None:
        data = members.get(f"{folder}/{name}" if folder else name)
        if data is None or len(data) > _MAX_IGNORE_FILE:
            return None
        return data.decode("utf-8", errors="replace")

    def marked(folder: str) -> bool:
        prefix = f"{folder}/" if folder else ""
        return prefix + "pyvenv.cfg" in members or _is_cachedir_tag(
            members.get(prefix + "CACHEDIR.TAG")
        )

    return IgnoreEngine(
        extra=list(opts.ignore),
        defaults=opts.defaults,
        hidden=opts.hidden,
        load=load,
        marked=marked,
    )


def _glob_filter(opts: TreeOptions):
    """``glob`` option -> predicate on file paths (gitignore-style patterns)."""
    if not opts.glob:
        return None
    rules = compile_rules(opts.glob)

    def keep(path: str) -> bool:
        result = False
        for rule in rules:
            if not rule.dir_only and rule.regex.fullmatch(path):
                result = not rule.negate
        return result

    return keep


# ---------------------------------------------------------------------------
# Wildcard patterns
# ---------------------------------------------------------------------------

_MAGIC = re.compile(r"[*?]|\[[^\]/]+\]")


def _has_magic(component: str) -> bool:
    return bool(_MAGIC.search(component))


def _looks_like_glob(s: str) -> bool:
    """True when ``s`` is a wildcard pattern: any part has ``*``, ``?`` or ``[..]``.

    Examples:
        >>> _looks_like_glob("docs/*.txt"), _looks_like_glob("src/**/x.py")
        (True, True)
        >>> _looks_like_glob("src/*/file.txt"), _looks_like_glob("file[1].txt")
        (True, True)
        >>> _looks_like_glob("plain/file.txt"), _looks_like_glob("odd[name")
        (False, False)
    """
    return any(_has_magic(c) for c in s.replace(os.sep, "/").split("/"))


def _split_pattern(pattern: str) -> tuple[str, list[str]]:
    """``(static base, remaining components)`` of a wildcard pattern.

    Examples:
        >>> _split_pattern("src/*/x.py")
        ('src', ['*', 'x.py'])
        >>> _split_pattern("/abs/dir/**/*.md")
        ('/abs/dir', ['**', '*.md'])
        >>> _split_pattern("*.py")
        ('', ['*.py'])
    """
    parts = pattern.replace(os.sep, "/").split("/")
    first = next(
        (i for i, part in enumerate(parts[:-1]) if _has_magic(part)), len(parts) - 1
    )
    base = "/".join(parts[:first])
    if base == "" and parts[0] == "" and first > 0:
        base = "/"  # "/*.py": the filesystem root
    return base, parts[first:]


def _valid_regex(regex: str) -> bool:
    try:
        re.compile(regex)
        return True
    except re.error:
        return False


def _component_regex(component: str, hidden: bool) -> str:
    """One glob component: ``*`` / ``?`` / ``[..]`` never cross ``/``.

    Like the shell (and Python's glob), a wildcard does not match a
    leading dot unless the component starts with one or ``hidden`` is on.
    """
    out: list[str] = []
    i = 0
    while i < len(component):
        c = component[i]
        if c == "*":
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            j = component.find(
                "]", i + 2 if component[i + 1 : i + 2] in ("!", "^") else i + 1
            )
            body = component[i + 1 : j] if j != -1 else ""
            if body[:1] in ("!", "^"):
                body = "^" + body[1:]
            group = "[" + body.replace("\\", "\\\\") + "]"
            if j == -1 or not _valid_regex(group):
                out.append(re.escape(c))  # not a valid set: a literal "["
            else:
                out.append(group)
                i = j
        else:
            out.append(re.escape(c))
        i += 1
    regex = "".join(out)
    if not hidden and not component.startswith(".") and _has_magic(component):
        regex = r"(?!\.)" + regex
    return regex


def _pattern_regex(components: list[str], hidden: bool) -> re.Pattern[str]:
    """Regex for paths relative to the static base.

    Examples:
        >>> r = _pattern_regex(["*", "x.py"], False)
        >>> bool(r.fullmatch("a/x.py")), bool(r.fullmatch("a/b/x.py"))
        (True, False)
        >>> r = _pattern_regex(["**", "*.md"], False)
        >>> [bool(r.fullmatch(p)) for p in ("a.md", "a/b/c.md", ".h/c.md")]
        [True, True, False]
    """
    dirs = "(?:[^/]+/)*" if hidden else r"(?:(?!\.)[^/]+/)*"
    regex = ""
    for i, comp in enumerate(components):
        last = i == len(components) - 1
        if comp == "**":
            regex += dirs + (
                ("(?!\\.)" if not hidden else "") + "[^/]+" if last else ""
            )
        else:
            regex += _component_regex(comp, hidden) + ("" if last else "/")
    return re.compile(regex, re.DOTALL)


# ---------------------------------------------------------------------------
# Listing a folder
# ---------------------------------------------------------------------------


@dataclass
class _Candidate:
    rel: str
    path: Path
    size: int


def _inside(path: Path, root_real: Path) -> bool:
    try:
        Path(os.path.realpath(path)).relative_to(root_real)
        return True
    except ValueError:
        return False


def _list_folder(
    root: Path,
    opts: TreeOptions,
    report: TreeReport,
    *,
    pattern: re.Pattern[str] | None = None,
    pattern_depth: int | None = None,
    pattern_components: list[str] | None = None,
    hidden_dirs: bool | None = None,
) -> list[_Candidate]:
    """Walk *root* (sorted), returning the files to consider, in order."""
    hidden = opts.hidden if hidden_dirs is None else hidden_dirs
    engine = folder_engine(root, opts, hidden=hidden)
    keep_glob = _glob_filter(opts)
    root_real = Path(os.path.realpath(root))
    candidates: list[_Candidate] = []
    scanned = 0
    stack: list[str] = [""]
    while stack:
        folder = stack.pop()
        try:
            with os.scandir(root / folder if folder else root) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError:
            report.skip(UNREADABLE, folder, folder=True)
            continue
        subfolders: list[str] = []
        for entry in entries:
            scanned += 1
            if scanned > MAX_SCAN_ENTRIES:
                report.scan_capped = True
                return candidates
            rel = f"{folder}/{entry.name}" if folder else entry.name
            try:
                is_link = entry.is_symlink()
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                report.skip(UNREADABLE, rel)
                continue
            if is_dir:
                # A pattern decides first which folders matter at all, so
                # skips are only reported where matches could have been.
                if pattern_depth is not None and rel.count("/") + 1 >= pattern_depth:
                    continue  # deeper than the pattern can reach
                if pattern_components is not None and not _could_match(
                    rel, pattern_components, hidden
                ):
                    continue
                reason = engine.check(rel, is_dir=True)
                if reason:
                    report.skip(reason, rel, folder=True)
                elif pattern is None and not opts.recursive:
                    report.skip(NOT_RECURSIVE, rel, folder=True)
                else:
                    subfolders.append(rel)
                continue
            if pattern is not None and not pattern.fullmatch(rel):
                continue
            if is_link:
                if not _inside(Path(entry.path), root_real):
                    report.skip(SYMLINK, rel)
                    continue
                if os.path.isdir(entry.path):
                    continue  # a link to a folder inside the tree: read it there
            try:
                info = os.stat(entry.path)
            except OSError:
                report.skip(UNREADABLE, rel)
                continue
            if not stat.S_ISREG(info.st_mode):
                report.skip(SPECIAL, rel)
                continue
            reason = engine.check(rel, is_dir=False)
            if reason:
                report.skip(reason, rel)
                continue
            if keep_glob is not None and not keep_glob(rel):
                report.skip(GLOB_OPTION, rel)
                continue
            candidates.append(_Candidate(rel, Path(entry.path), info.st_size))
        # Depth-first in sorted order: files of a folder, then its subfolders.
        stack.extend(reversed(subfolders))
    return candidates


def _could_match(folder: str, components: list[str], hidden: bool) -> bool:
    """Whether files under *folder* can match a pattern without ``**``."""
    parts = folder.split("/")
    for part, comp in zip(parts, components, strict=False):
        if not re.fullmatch(_component_regex(comp, hidden), part):
            return False
    return True


# ---------------------------------------------------------------------------
# Reading within limits
# ---------------------------------------------------------------------------


class _Budget:
    def __init__(self, opts: TreeOptions, report: TreeReport) -> None:
        self.files_left = opts.max_files or None
        self.bytes_left = opts.max_size or None
        self.report = report

    def take(self, size: int) -> bool:
        """Reserve room for one file of *size* bytes; ``False`` if it doesn't fit."""
        if self.files_left is not None and self.files_left <= 0:
            self._hit("max_files")
            return False
        if self.bytes_left is not None and size > self.bytes_left:
            self._hit("max_size")
            return False
        if self.files_left is not None:
            self.files_left -= 1
        if self.bytes_left is not None:
            self.bytes_left -= size
        return True

    def _hit(self, limit: str) -> None:
        self.report.not_read += 1
        if self.report.limit is None:
            self.report.limit = limit


def _expand_members(
    archive_rel: str,
    data: bytes,
    opts: TreeOptions,
    report: TreeReport,
    budget: _Budget,
) -> list[SourceFile]:
    """Members of an archive that pass the skip rules and the limits."""
    from .archives import _explode_archive_bytes

    members = _explode_archive_bytes("", data)
    by_name = dict(members)
    engine = member_engine(by_name, opts)
    keep_glob = _glob_filter(opts)
    out: list[SourceFile] = []
    for name, content in members:
        shown = f"{archive_rel}/{name}" if archive_rel else name
        reason = engine.check_path(name)
        if reason:
            report.skip(reason, shown)
            continue
        if keep_glob is not None and not keep_glob(name):
            report.skip(GLOB_OPTION, shown)
            continue
        if not budget.take(len(content)):
            continue
        out.append(SourceFile(shown, content))
    return out


def read_tree(
    candidates: list[_Candidate], opts: TreeOptions, report: TreeReport
) -> list[SourceFile]:
    """Read listed files within the limits (``files: false`` reads nothing)."""
    from .archives import _is_raw_archive_name

    budget = _Budget(opts, report)
    out: list[SourceFile] = []
    for candidate in candidates:
        if not opts.files:
            if budget.take(candidate.size):
                report.entries.append(Entry(candidate.rel, candidate.size))
            continue
        if not budget.take(candidate.size):
            continue
        try:
            with open(candidate.path, "rb") as fh:
                data = fh.read()
        except OSError:
            report.skip(UNREADABLE, candidate.rel)
            continue
        if _is_raw_archive_name(candidate.rel):
            # The archive itself took one slot; its members are what counts.
            if budget.files_left is not None:
                budget.files_left += 1
            if budget.bytes_left is not None:
                budget.bytes_left += candidate.size
            members = _expand_members(candidate.rel, data, opts, report, budget)
            report.entries.append(Entry(candidate.rel, candidate.size, len(members)))
            out.extend(members)
        else:
            report.entries.append(Entry(candidate.rel, len(data)))
            out.append(SourceFile(candidate.rel, data))
    return out


# ---------------------------------------------------------------------------
# Entry points used by unpack()
# ---------------------------------------------------------------------------


def _attach_git(report: TreeReport, root: Path) -> None:
    repo = find_repo_root(root)
    if repo is not None:
        report.git = read_git_info(repo)


def read_folder(
    path: Path,
    opts: TreeOptions,
    *,
    label: str,
    kind: str = "folder",
    root_name: str | None = None,
) -> tuple[list[SourceFile], TreeReport]:
    """A folder on disk: its files (per the options) and the report."""
    root = path.resolve()
    report = TreeReport(label, kind, root_name or root.name or str(root), opts)
    candidates = _list_folder(root, opts, report)
    files = read_tree(candidates, opts, report)
    _attach_git(report, root)
    return files, report


def read_archive(
    name: str, data: bytes, opts: TreeOptions, *, label: str
) -> tuple[list[SourceFile], TreeReport]:
    """An archive given directly: its members (per the options) and the report."""
    report = TreeReport(label, "archive", name, opts)
    budget = _Budget(opts, report)
    if not opts.files:
        from .archives import _explode_archive_bytes

        members = _explode_archive_bytes("", data)
        engine = member_engine(dict(members), opts)
        for member, content in members:
            reason = engine.check_path(member)
            if reason:
                report.skip(reason, member)
            elif budget.take(len(content)):
                report.entries.append(Entry(member, len(content)))
        return [], report
    members = _expand_members(name, data, opts, report, budget)
    for member in members:
        report.entries.append(Entry(member.name[len(name) + 1 :], len(member.data)))
    return members, report


def read_pattern(
    pattern: str, opts: TreeOptions
) -> tuple[list[SourceFile], TreeReport]:
    """Files matching a wildcard pattern, named relative to its static base."""
    base, components = _split_pattern(pattern)
    root = Path(base or ".")
    report = TreeReport(pattern, "pattern", base or ".", opts)
    if not root.is_dir():
        raise ValueError(_no_match_message(pattern, report))
    # Wildcards skip dot names unless the pattern spells a leading dot, so
    # hidden folders are only searched when the pattern can reach into one.
    needs_hidden = opts.hidden or any(c.startswith(".") for c in components)
    regex = _pattern_regex(components, opts.hidden)
    has_globstar = "**" in components
    candidates = _list_folder(
        root.resolve(),
        opts,
        report,
        pattern=regex,
        pattern_depth=None if has_globstar else len(components),
        pattern_components=None if has_globstar else components,
        hidden_dirs=True if needs_hidden else opts.hidden,
    )
    if not candidates and opts.files:
        raise ValueError(_no_match_message(pattern, report))
    files = read_tree(candidates, opts, report)
    _attach_git(report, root.resolve())
    return files, report


#: Skip reasons the ignore rules decide (``[ignore: none]`` lifts them).
_RULE_REASONS = frozenset(
    {"ignore option", "secret", "generated", "hidden", "ignore file"}
)


def _no_match_message(pattern: str, report: TreeReport | None = None) -> str:
    """Error for a pattern with zero files, explaining skips and DSL mistakes.

    A bracket group that fails the DSL grammar (an unquoted comma in a
    value: ``page.html[select: h1,p]``) stays in the source and arrives here
    because ``[`` is a wildcard character. When the text before the final
    ``[...]`` names an existing file, say that instead.
    """
    msg = f"Glob pattern matched no files: {pattern}"
    hint = _dsl_hint(msg, pattern)
    if hint:
        return hint  # the real problem: options written outside the grammar
    if report is not None and report.skipped:
        counts = ", ".join(
            f"{reason}: {s.files + s.folders}"
            for reason, s in report.skipped.items()
            if reason in _RULE_REASONS
        )
        if counts:
            msg += (
                f" — skipped: {counts} (matching files, or folders that were "
                "not searched); "
                "add [ignore: none] (and [hidden: true] for dot files) to include them"
            )
    return msg


def _dsl_hint(msg: str, pattern: str) -> str | None:
    """The message for a malformed ``[...]`` options block after a real file."""
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
    return None
