"""``att.from_prompt``: attach the files a prompt mentions.

    a = att.from_prompt("Compare `report.pdf[pages: 1-3]` with data.csv")
    a.claude("Compare report.pdf with data.csv")

Successor of 0.25's ``auto_attach``. What counts as a mention:

- text in backticks or quotes (``"my notes.txt"``) — may name a folder;
- a bare word with a file extension (``data.csv``, ``src/app.py``),
  optionally followed by DSL options (``report.pdf[pages: 1-3]``);
- ``http(s)://`` addresses, only with ``urls=True``.

Only mentions that exist are attached; words that merely look like file
names ("Node.js", "e.g.") are ignored. Results keep the order of first
mention, without duplicates.

Prompts are often written by someone other than the developer (a chat
user, an email, a web form), so mentions are treated as untrusted:

- they resolve only INSIDE the given root folders (default: the current
  folder) — no ``..``, absolute paths or links leading out;
- files that look like secrets (``.env``, private keys, ...) are never
  attached from a prompt — call ``att()`` directly for those;
- URLs are off by default: fetching an address chosen by the prompt's
  author is a server-side request forgery risk. With ``urls=True`` the
  usual ``ATT_BLOCK_PRIVATE_URLS`` guard applies.

Skipped mentions are logged (``attachments.mentions`` logger, INFO).
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._artifacts import Artifacts
from ._sources._ignore import is_secret
from .dsl import parse_dsl

log = logging.getLogger("attachments.mentions")

_QUOTED = re.compile(
    r"`([^`\n]+)`"  # backticks
    r'|"([^"\n]+)"'  # double quotes
    r"|“([^”\n]+)”"  # curly double quotes
    r"|(?<![\w])'([^'\n]+)'(?![\w])"  # single quotes (not apostrophes)
    r"|‘([^’\n]+)’"  # curly single quotes
)
_URL = re.compile(r"https?://[^\s<>\"'`]+")
_BARE = re.compile(
    r"(?<![\w@/~.-])"  # not inside a word, an email or a longer path
    r"((?:~|\.{1,2})?/?(?:[\w.-]+/)*[\w-][\w.-]*\.[A-Za-z0-9]{1,10})"
    r"(\[[^\]\n]*\])?"  # optional DSL options
)
_TRAILING = ".,;:!?"


@dataclass(frozen=True)
class Mention:
    text: str  # path or URL as written, DSL options included
    explicit: bool  # quoted or in backticks: may name a folder
    url: bool
    start: int


def _strip_url(url: str) -> str:
    """Drop sentence punctuation and an unbalanced closing parenthesis."""
    dsl = ""
    match = re.search(r"\[[^\]]*\]$", url)
    if match:
        url, dsl = url[: match.start()], match.group(0)
    url = url.rstrip(_TRAILING)
    while url.endswith(")") and url.count(")") > url.count("("):
        url = url[:-1].rstrip(_TRAILING)
    return url + dsl


def find_mentions(prompt: str) -> list[Mention]:
    """Candidate file/URL mentions in *prompt*, in order of appearance.

    Examples:
        >>> [
        ...     m.text
        ...     for m in find_mentions(
        ...         "Read `notes/a b.txt`, data.csv and report.pdf[pages: 1-2]. "
        ...         "Mail me@x.org, see https://x.org/p.pdf). It's fine."
        ...     )
        ... ]
        ['notes/a b.txt', 'data.csv', 'report.pdf[pages: 1-2]', 'https://x.org/p.pdf']
    """
    found: list[Mention] = []
    taken: list[tuple[int, int]] = []

    def free(start: int, end: int) -> bool:
        return all(end <= a or start >= b for a, b in taken)

    for match in _QUOTED.finditer(prompt):
        text = next(g for g in match.groups() if g is not None).strip()
        if not text:
            continue
        taken.append(match.span())
        is_url = bool(_URL.fullmatch(text.split("[", 1)[0]))
        found.append(Mention(text, True, is_url, match.start()))
    for match in _URL.finditer(prompt):
        if free(*match.span()):
            taken.append(match.span())
            found.append(
                Mention(_strip_url(match.group(0)), False, True, match.start())
            )
    for match in _BARE.finditer(prompt):
        if free(*match.span()):
            text = match.group(1).rstrip(".") + (match.group(2) or "")
            taken.append(match.span())
            found.append(Mention(text, False, False, match.start()))
    found.sort(key=lambda m: m.start)
    return found


def _roots(root: Any) -> list[Path]:
    if root is None:
        return [Path.cwd()]
    if isinstance(root, str | os.PathLike):
        root = [root]
    return [Path(os.path.realpath(os.fspath(r))) for r in root]


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _locate(path_text: str, roots: Iterable[Path], explicit: bool) -> Path | None:
    """The existing file (or, if explicit, folder) a mention names, if allowed."""
    if path_text.startswith("~"):
        return None  # a home directory is never inside a root by design
    for root in roots:
        candidate = Path(path_text)
        if not candidate.is_absolute():
            candidate = root / candidate
        real = Path(os.path.realpath(candidate))
        if not _within(real, root):
            continue
        if real.is_file() or (explicit and real.is_dir()):
            return real
    return None


def from_prompt(
    prompt: str,
    *,
    root: str | os.PathLike[str] | Iterable[str | os.PathLike[str]] | None = None,
    urls: bool = False,
    api_key: str | None = None,
    prefer: str | None = None,
    **options: Any,
) -> Artifacts:
    """Attach the files (and, with ``urls=True``, web pages) *prompt* mentions.

    Args:
        prompt: Text that names files, e.g. a user's question.
        root: Folder(s) mentions are looked up in, and confined to
            (default: the current folder).
        urls: Also fetch ``http(s)://`` addresses in the prompt.
        api_key, prefer, **options: As for ``att()``; options apply to
            every attached file (options written in the prompt win).

    Returns:
        ``Artifacts`` in order of first mention — empty if nothing matched.
        The prompt itself is not included: pass it to ``.claude(prompt)``.
    """
    from .core import att

    roots = _roots(root)
    seen: set[tuple[str, tuple]] = set()
    out = Artifacts()
    for mention in find_mentions(prompt):
        path_text, dsl = parse_dsl(mention.text)
        if mention.url:
            if not urls:
                log.info("not fetching %s (from_prompt urls=False)", path_text)
                continue
            key = (path_text, tuple(sorted(dsl.items(), key=str)))
            if key in seen:
                continue
            seen.add(key)
            out.extend(att(mention.text, api_key=api_key, prefer=prefer, **options))
            continue
        located = _locate(path_text, roots, mention.explicit)
        if located is None:
            log.info("no file %r inside %s", path_text, [str(r) for r in roots])
            continue
        relative = next(
            (located.relative_to(r).as_posix() for r in roots if _within(located, r)),
            located.name,
        )
        if located.is_file() and is_secret(relative):
            log.info("not attaching %r from a prompt: looks like a secret", path_text)
            continue
        key = (str(located), tuple(sorted(dsl.items(), key=str)))
        if key in seen:
            continue
        seen.add(key)
        artifacts = att([located], api_key=api_key, prefer=prefer, **{**options, **dsl})
        for artifact in artifacts:
            # Name it as the prompt did ("src/app.py"), not by its basename
            # or an absolute path that would leak the machine's layout.
            if artifact["meta"].get("source") in (str(located), located.name):
                artifact["meta"]["source"] = path_text
        out.extend(artifacts)
    return out
