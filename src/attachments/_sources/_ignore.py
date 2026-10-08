"""Which files in a folder are skipped, and why.

One engine decides for every tree of files attachments reads — local
folders, wildcard patterns, cloned GitHub repos and archives — so the
same folder gives the same files however it arrives.

Layers, checked in this order (the first that decides wins):

1. **Version-control folders** (``.git``, ``.hg``, ``.svn``, ...): always.
2. **The ``ignore`` option**: extra patterns in ``.gitignore`` syntax. A
   ``!pattern`` here re-includes something a later layer would skip
   (``ignore: "!package-lock.json"``).
3. **Secrets** (``.env`` files, private keys, credential files): skipped
   because they end up in a prompt sent to someone else's server.
4. **Generated files** (dependency folders, virtual environments, caches,
   lock files, compiled objects, minified bundles, OS clutter). Folders
   are recognised by precise markers where names would be ambiguous: a
   Python virtual environment holds ``pyvenv.cfg``; cache folders carry
   the standard ``CACHEDIR.TAG`` (Cargo's ``target/``, pytest, mypy, ruff).
   Names like ``build``, ``bin`` or ``vendor`` are NOT guessed: they hold
   real code often enough; a project's ``.gitignore`` says when they don't.
5. **Hidden files and folders** (name starts with ``.``), unless
   ``hidden: true`` — the convention of ripgrep and fd.
6. **Ignore files**: ``.gitignore`` and ``.attachmentsignore`` in the
   folder and its subfolders, the ``.gitignore`` files of parent folders
   up to the repository root, and ``.git/info/exclude``. Full gitignore
   semantics: anchoring, ``**``, character classes, ``!`` negation,
   directory-only patterns, and deeper files overriding shallower ones.
   Unlike git, ``.gitignore`` is honoured outside a repository too (a
   downloaded source archive keeps its intent).

``ignore: none`` turns off layers 3-6 (version-control folders stay out).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

#: Reasons a file or folder was skipped (stable keys used in reports).
VCS = "vcs"
OPTION = "ignore option"
SECRET = "secret"
GENERATED = "generated"
HIDDEN = "hidden"
IGNORE_FILE = "ignore file"

VCS_DIRS = frozenset({".git", ".hg", ".svn", ".bzr", "_darcs", ".jj", ".pijul"})

#: Names of the ignore files read in every folder (later = higher priority).
IGNORE_FILES = (".gitignore", ".attachmentsignore")

SECRET_PATTERNS = (
    # dotenv files (examples and templates are documentation, keep them)
    ".env",
    ".env.*",
    "!.env.example",
    "!.env.sample",
    "!.env.template",
    "!.env.dist",
    "!.env.defaults",
    # private keys, keystores, password databases
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.jks",
    "*.keystore",
    "*.kdbx",
    "*.ppk",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    # credential stores
    ".netrc",
    "_netrc",
    ".pgpass",
    ".npmrc",
    ".pypirc",
    ".git-credentials",
    ".htpasswd",
    "**/.aws/credentials",
    "**/.docker/config.json",
    "client_secret*.json",
    # Terraform state holds every secret it manages, in clear text
    "*.tfstate",
    "*.tfstate.backup",
)

GENERATED_PATTERNS = (
    # dependency folders
    "node_modules/",
    "bower_components/",
    "jspm_packages/",
    "site-packages/",
    "*.egg-info/",
    "__pycache__/",
    # lock files: long, machine-written, no meaning for a reader
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lock",
    "bun.lockb",
    "poetry.lock",
    "Pipfile.lock",
    "pdm.lock",
    "uv.lock",
    "Cargo.lock",
    "Gemfile.lock",
    "composer.lock",
    "go.sum",
    "mix.lock",
    "Podfile.lock",
    "pubspec.lock",
    "packages.lock.json",
    "flake.lock",
    # compiled objects and libraries
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.class",
    "*.o",
    "*.obj",
    "*.so",
    "*.dylib",
    "*.dll",
    "*.a",
    "*.lib",
    "*.exe",
    # minified bundles and source maps
    "*.min.js",
    "*.min.css",
    "*.map",
    # operating-system clutter
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
)

#: First line of a valid CACHEDIR.TAG (https://bford.info/cachedir/).
CACHEDIR_SIGNATURE = b"Signature: 8a477f597d28d172789f06886806bc55"


# ---------------------------------------------------------------------------
# gitignore patterns
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    """One compiled gitignore line."""

    regex: re.Pattern[str]
    negate: bool
    dir_only: bool
    text: str


def _class(pattern: str, i: int) -> tuple[str, int]:
    """Translate a ``[...]`` class starting at *i*; ``('', i)`` if unclosed."""
    j = i + 1
    if j < len(pattern) and pattern[j] in "!^":
        j += 1
    if j < len(pattern) and pattern[j] == "]":
        j += 1
    while j < len(pattern) and pattern[j] != "]":
        j += 1
    if j >= len(pattern):
        return "", i
    body = pattern[i + 1 : j]
    negate = body[:1] in ("!", "^")
    if negate:
        body = body[1:]
    body = body.replace("\\", "\\\\").replace("/", "")
    if body.startswith("]"):
        body = "\\" + body
    return ("[^/" if negate else "[") + body + "]", j + 1


def _segment_regex(segment: str) -> str:
    """Regex for one path segment (``*``, ``?``, ``[...]``, ``\\x``)."""
    out: list[str] = []
    i = 0
    while i < len(segment):
        c = segment[i]
        if c == "\\" and i + 1 < len(segment):
            out.append(re.escape(segment[i + 1]))
            i += 2
        elif c == "*":
            while i < len(segment) and segment[i] == "*":
                i += 1
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "[":
            translated, j = _class(segment, i)
            if translated:
                out.append(translated)
                i = j
            else:
                out.append(re.escape(c))
                i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return "".join(out)


def translate_gitignore(pattern: str) -> str:
    """Regex (for ``fullmatch``) of a gitignore pattern body.

    *pattern* has had its ``!`` prefix and trailing ``/`` removed. Paths
    are relative to the directory of the ignore file, ``/``-separated.

    Examples:
        >>> import re
        >>> def m(p, path):
        ...     return bool(re.fullmatch(translate_gitignore(p), path))
        >>> m("*.log", "a/b/debug.log"), m("/*.log", "a/debug.log")
        (True, False)
        >>> m("doc/*.txt", "doc/x.txt"), m("doc/*.txt", "doc/sub/x.txt")
        (True, False)
        >>> m("**/foo", "a/b/foo"), m("a/**/b", "a/b"), m("a/**/b", "a/x/y/b")
        (True, True, True)
        >>> m("abc/**", "abc/x/y"), m("abc/**", "abc")
        (True, False)
        >>> m("file[0-9].txt", "file7.txt"), m("\\\\#notes", "#notes")
        (True, True)
    """
    anchored = pattern.startswith("/") or "/" in pattern.rstrip("/")
    pattern = pattern.lstrip("/")
    parts = pattern.split("/")
    regex: list[str] = []
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        if part == "**":
            if last:
                regex.append(".*" if index == 0 else ".+")
            else:
                regex.append("(?:[^/]+/)*")
            continue
        regex.append(_segment_regex(part))
        if not last:
            regex.append("/")
    body = "".join(regex)
    return body if anchored else "(?:.*/)?" + body


def compile_rule(line: str) -> Rule | None:
    """Compile one line of an ignore file (``None`` for blanks/comments).

    Examples:
        >>> compile_rule("# comment") is None, compile_rule("   ") is None
        (True, True)
        >>> r = compile_rule("!build/")
        >>> r.negate, r.dir_only, r.text
        (True, True, '!build/')
    """
    text = line.rstrip("\n").rstrip("\r")
    # Trailing spaces are ignored unless escaped with a backslash.
    stripped = re.sub(r"(?<!\\)\s+$", "", text)
    if not stripped or stripped.startswith("#"):
        return None
    body = stripped
    negate = body.startswith("!")
    if negate:
        body = body[1:]
    elif body.startswith(("\\!", "\\#")):
        body = body[1:]
    dir_only = body.endswith("/")
    body = body.rstrip("/")
    if not body:
        return None
    try:
        regex = re.compile(translate_gitignore(body), re.DOTALL)
    except re.error:
        return None
    return Rule(regex, negate, dir_only, stripped)


def compile_rules(lines: Iterable[str]) -> list[Rule]:
    return [r for r in (compile_rule(line) for line in lines) if r is not None]


def split_patterns(value: str | Iterable[str] | None) -> list[str]:
    """Option value -> patterns: a list, or a comma/newline separated string.

    Examples:
        >>> split_patterns("*.log, tests/ ,!keep.log")
        ['*.log', 'tests/', '!keep.log']
        >>> split_patterns(["a", " b "])
        ['a', 'b']
    """
    if value is None:
        return []
    if isinstance(value, str):
        value = re.split(r"[,\n]", value)
    return [p.strip() for p in value if p and p.strip()]


def _decide(rules: list[Rule], path: str, is_dir: bool) -> bool | None:
    """Last matching rule: ``True`` ignored, ``False`` re-included, else None."""
    result: bool | None = None
    for rule in rules:
        if rule.dir_only and not is_dir:
            continue
        if rule.regex.fullmatch(path):
            result = not rule.negate
    return result


_SECRET_RULES = compile_rules(SECRET_PATTERNS)
_GENERATED_RULES = compile_rules(GENERATED_PATTERNS)


def is_secret(path: str) -> bool:
    """Whether *path* (any ``/``-separated relative path) looks like a secret.

    Examples:
        >>> is_secret("config/.env"), is_secret(".env.example"), is_secret("a.py")
        (True, False, False)
        >>> is_secret("home/.aws/credentials"), is_secret("deploy/id_ed25519")
        (True, True)
    """
    return bool(_decide(_SECRET_RULES, path, False))


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------

#: Reads ignore-file text for a folder (relative path, "" = root); ``None``
#: when it does not exist.
IgnoreLoader = Callable[[str, str], str | None]
#: Tells whether a folder is generated by its marker (pyvenv.cfg, CACHEDIR.TAG).
MarkerCheck = Callable[[str], bool]


@dataclass
class IgnoreEngine:
    """Decides, for paths relative to one root, whether to skip them.

    Args:
        extra: patterns from the ``ignore`` option.
        defaults: apply layers 3-6 (``False`` = ``ignore: none``).
        hidden: include hidden files and folders.
        load: reads an ignore file in a folder of this tree.
        marked: tells whether a folder is generated (marker files).
        outer: rules from ignore files ABOVE the root (parent folders up
            to the repository root, ``.git/info/exclude``), each with the
            prefix that turns a root-relative path into a path relative
            to that file's folder. Highest priority first.
    """

    extra: list[str] = field(default_factory=list)
    defaults: bool = True
    hidden: bool = False
    load: IgnoreLoader | None = None
    marked: MarkerCheck | None = None
    outer: list[tuple[str, list[Rule]]] = field(default_factory=list)
    _extra_rules: list[Rule] = field(init=False, repr=False)
    _cache: dict[str, list[Rule]] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self._extra_rules = compile_rules(self.extra)

    def _folder_rules(self, folder: str) -> list[Rule]:
        """Rules of the ignore files in *folder* (later file = higher priority)."""
        if folder not in self._cache:
            rules: list[Rule] = []
            if self.load is not None:
                for name in IGNORE_FILES:
                    text = self.load(folder, name)
                    if text:
                        rules.extend(compile_rules(text.splitlines()))
            self._cache[folder] = rules
        return self._cache[folder]

    def check(self, path: str, *, is_dir: bool) -> str | None:
        """The reason *path* is skipped, or ``None`` to keep it.

        *path* is relative to the root, ``/``-separated; its parent
        folders are assumed already checked (the walk prunes them).

        Examples:
            >>> e = IgnoreEngine()
            >>> e.check(".git", is_dir=True), e.check("src/.env", is_dir=False)
            ('vcs', 'secret')
            >>> e.check("node_modules", is_dir=True), e.check(".idea", is_dir=True)
            ('generated', 'hidden')
            >>> e.check("src/app.py", is_dir=False) is None
            True
            >>> IgnoreEngine(extra=["!uv.lock"]).check("uv.lock", is_dir=False) is None
            True
            >>> IgnoreEngine(defaults=False).check(".env", is_dir=False) is None
            True
        """
        name = path.rsplit("/", 1)[-1]
        if is_dir and name in VCS_DIRS:
            return VCS
        decided = _decide(self._extra_rules, path, is_dir)
        if decided is not None:
            return OPTION if decided else None
        if not self.defaults:
            return None
        if _decide(_SECRET_RULES, path, is_dir):
            return SECRET
        if _decide(_GENERATED_RULES, path, is_dir):
            return GENERATED
        if is_dir and self.marked is not None and self.marked(path):
            return GENERATED
        if not self.hidden and name.startswith("."):
            return HIDDEN
        return IGNORE_FILE if self._ignored_by_files(path, is_dir) else None

    def _ignored_by_files(self, path: str, is_dir: bool) -> bool:
        parts = path.split("/")
        # Deepest folder first: a closer ignore file overrides a farther one.
        for depth in range(len(parts) - 1, -1, -1):
            folder = "/".join(parts[:depth])
            rules = self._folder_rules(folder)
            if rules:
                decided = _decide(rules, "/".join(parts[depth:]), is_dir)
                if decided is not None:
                    return decided
        for prefix, rules in self.outer:
            decided = _decide(rules, prefix + path, is_dir)
            if decided is not None:
                return decided
        return False

    def check_path(self, path: str) -> str | None:
        """Check a file path including every parent folder (no pruning walk).

        Used for flat lists of paths, like archive members.

        Examples:
            >>> e = IgnoreEngine()
            >>> e.check_path("pkg/node_modules/x/index.js")
            'generated'
            >>> e.check_path("pkg/src/x.js") is None
            True
        """
        parts = path.split("/")
        for depth in range(1, len(parts)):
            reason = self.check("/".join(parts[:depth]), is_dir=True)
            if reason:
                return reason
        return self.check(path, is_dir=False)
