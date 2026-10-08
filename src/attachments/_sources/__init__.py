"""Source resolution: turn an input string into ``(filename, bytes)`` pairs.

This package is the WHERE half of attachments (``_processors/`` is the
WHAT half). One module per source, mirroring the processor layout:

- ``local.py``    — folders, wildcard patterns and archive members, read
  in two steps (list, then read within limits) with a ``TreeReport``
- ``_ignore.py``  — the skip rules every tree shares (secrets, generated
  files, hidden files, ``.gitignore``, the ``ignore`` option)
- ``_git.py``     — branch/commit/remote, read from ``.git`` (never run)
- ``archives.py`` — zip/tar expansion (recursive, bomb-guarded)
- ``http.py``     — http(s) single-file download (optional SSRF guard)
- ``github.py``   — ``github://owner/repo`` + github.com repo roots
- ``_file.py``    — ``SourceFile``: a ``(name, bytes)`` pair with a URL
- ``_guards.py``  — shared security machinery (expansion budget,
  member-name sanitization, SSRF guard, size caps)

``resolve()`` returns files plus reports; ``unpack()`` is its files only.
Dispatch order — preserved exactly, do not reorder:

1. Custom prefix handlers: global ``extra_unpack_handlers`` (filled by
   ``register_unpack_handler`` / ``@source``) updated with the per-call
   ``extra_handlers`` dict; the first matching prefix wins.
2. GitHub repo roots: ``github://...`` or ``https://github.com/owner/repo``
   (deeper github.com URLs fall through to plain HTTP download).
3. HTTP(S) URLs: single-file download; archives expanded by extension.
4. Local directory (``file://`` URIs and ``~`` are local paths): sorted
   walk with the skip rules and limits.
5. Local file: read as-is; archives expanded by extension.
6. Wildcard pattern: ``* ? [..]`` in any part, ``**`` for any depth —
   names relative to the static base. Checked AFTER the ``exists()``
   checks, so a literal file named ``file[1].txt`` wins.
7. Anything else raises ``ValueError``.

Contributor note: to add a new source, add one module in this package,
register it at import time via the relative import ``from . import source``
(``from attachments import source`` is circular inside this package), and
add an import line for built-ins in the block at the BOTTOM of this file —
after the registry below is defined. A top-of-file import runs before
``source``/``register_unpack_handler`` exist and breaks all of
``import attachments`` with a circular ImportError. Add tests too — see
DEVELOPMENT.md ("Building New Sources").
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .._options import snapshot_option_defaults

if TYPE_CHECKING:
    from .local import TreeOptions, TreeReport

# Public registry for custom scheme handlers (prefix -> handler function)
extra_unpack_handlers: dict[str, Callable[[str], list[tuple[str, bytes]]]] = {}


def register_unpack_handler(
    prefix: str,
    handler: Callable[[str], list[tuple[str, bytes]]] | None = None,
) -> Callable:
    """Register a custom handler for an input prefix/scheme.

    Can be used as a function or decorator:

        # As a function
        register_unpack_handler("dropbox://", my_dropbox_handler)

        # As a decorator
        @register_unpack_handler("s3://")
        def s3_handler(url: str) -> list[tuple[str, bytes]]:
            ...

    The handler must accept the original input string and return a list of
    ``(filename, bytes)`` tuples.

    Args:
        prefix: URL scheme or prefix (e.g., "s3://", "dropbox://")
        handler: Handler function (optional if using as decorator)

    Returns:
        The registered function (for decorator use)

    Examples:
        >>> # Using as a function
        >>> def my_handler(url: str) -> list[tuple[str, bytes]]:
        ...     return [("test.txt", b"hello")]
        >>> register_unpack_handler("myscheme://", my_handler)  # doctest: +ELLIPSIS
        <function my_handler at ...>
        >>> "myscheme://" in extra_unpack_handlers
        True

        >>> # Clean up
        >>> del extra_unpack_handlers["myscheme://"]
    """

    def decorator(
        fn: Callable[[str], list[tuple[str, bytes]]],
    ) -> Callable[[str], list[tuple[str, bytes]]]:
        extra_unpack_handlers[prefix] = fn
        return fn

    # Called as @register_unpack_handler("s3://") - returns decorator
    if handler is None:
        return decorator

    # Called as register_unpack_handler("s3://", func) - register directly
    extra_unpack_handlers[prefix] = handler
    return handler


def source(*prefixes: str) -> Callable:
    """Decorator to register an unpack handler for multiple prefixes.

    Example:
        @source("s3://", "s3a://", "s3n://")
        def s3_handler(url: str) -> list[tuple[str, bytes]]:
            ...

    Args:
        *prefixes: One or more URL prefixes to register

    Returns:
        Decorator function
    """

    def decorator(
        fn: Callable[[str], list[tuple[str, bytes]]],
    ) -> Callable[[str], list[tuple[str, bytes]]]:
        for prefix in prefixes:
            extra_unpack_handlers[prefix] = fn
        return fn

    return decorator


@dataclass
class Resolution:
    """What an input resolved to: files, plus a report per tree read.

    ``files`` are ``(name, bytes)`` pairs (``SourceFile`` for downloads and
    tree members). ``reports`` describe each folder, pattern, repository or
    archive: what was read and what was skipped, and why.
    """

    files: list[tuple[str, bytes]]
    reports: list[TreeReport] = field(default_factory=list)


def _local_path(input: str) -> str:
    """``file://`` URIs and ``~`` become plain local paths.

    Examples:
        >>> _local_path("file:///tmp/a%20b.txt")
        '/tmp/a b.txt'
        >>> _local_path("file://localhost/tmp/x")
        '/tmp/x'
        >>> _local_path("notes.txt")
        'notes.txt'
    """
    if input.startswith("file://"):
        from urllib.parse import unquote, urlsplit
        from urllib.request import url2pathname

        parts = urlsplit(input)
        if parts.netloc not in ("", "localhost"):
            raise ValueError(
                f"file:// URIs must name a local file (no host), got {input!r}"
            )
        return url2pathname(unquote(parts.path))
    if input.startswith("~"):
        return os.path.expanduser(input)
    return input


def resolve(
    input: str,
    extra_handlers: dict[str, Callable[[str], list[tuple[str, bytes]]]] | None = None,
    *,
    block_private_urls: bool | None = None,
    options: dict[str, Any] | TreeOptions | None = None,
) -> Resolution:
    """Resolve an input into files and per-tree reports (see ``unpack``).

    ``options`` are the folder options (``files``, ``tree``, ``ignore``,
    ``hidden``, ``glob``, ``recursive``, ``max_files``, ``max_size``),
    applied to folders, wildcard patterns, repositories and archives.
    Invalid values raise ``InvalidSourceOption``.
    """
    if isinstance(options, TreeOptions):
        opts, warnings = options, []
    else:
        opts, warnings = TreeOptions.from_options(options)

    def done(files, report=None) -> Resolution:
        if report is None:
            return Resolution(list(files))
        report.warnings.extend(warnings)
        return Resolution(list(files), [report])

    # Custom handlers (global then per-call)
    handlers = dict(extra_unpack_handlers)
    if extra_handlers:
        handlers.update(extra_handlers)
    for prefix, handler in handlers.items():
        if input.startswith(prefix):
            return done(handler(input))

    # GitHub repo shorthand/scheme (repo root ONLY)
    if input.startswith("github://") or _is_github_repo_root_url(input):
        tmpdir = _clone_github_to_temp(input)
        try:
            files, report = read_folder(
                tmpdir,
                opts,
                label=input,
                kind="repo",
                root_name=_github_display_name(input),
            )
        finally:
            # Contents are in memory now; a clone per call must not pile up.
            shutil.rmtree(tmpdir, ignore_errors=True)
        return done(files, report)

    # HTTP/HTTPS single-file download (deeper github.com URLs land here)
    if input.startswith("http://") or input.startswith("https://"):
        downloaded = _download_http_or_https(
            input, block_private_urls=block_private_urls
        )
        name, data = downloaded
        if _is_raw_archive_name(name):
            return done(*read_archive(name, data, opts, label=input))
        # A SourceFile: still a (name, bytes) pair, plus the final URL.
        return done([downloaded])

    local = _local_path(input)
    p = Path(local)

    # Local directory
    if p.exists() and p.is_dir():
        return done(*read_folder(p, opts, label=input))

    # Local file (a single named file is read as asked: no skip rules)
    if p.exists() and p.is_file():
        with open(p, "rb") as f:
            data = f.read()
        if _is_raw_archive_name(p.name):
            return done(*read_archive(p.name, data, opts, label=input))
        return done([(p.name, data)])

    # Wildcard pattern — after the exists() checks, so a literal file named
    # e.g. "file[1].txt" wins over pattern interpretation.
    if _looks_like_glob(local):
        return done(*read_pattern(local, opts))

    raise ValueError(f"Unsupported or non-existent input: {input}")


def unpack(
    input: str,
    extra_handlers: dict[str, Callable[[str], list[tuple[str, bytes]]]] | None = None,
    *,
    block_private_urls: bool | None = None,
    options: dict[str, Any] | None = None,
) -> list[tuple[str, bytes]]:
    """Resolve an input path/spec into a flat list of ``(filename, bytes)``.

    Supported out-of-the-box:
      - Local directory: recursive, sorted walk. Secrets, generated files,
        hidden files and whatever ``.gitignore`` / ``.attachmentsignore``
        exclude are skipped; at most ``max_files`` files and ``max_size``
        bytes are read (folder options, see ``_sources/local.py``).
      - Local files (``file://`` URIs and ``~`` work too). A single named
        file is always read. ZIP/TAR archives are expanded, with the same
        skip rules and limits applied to their members.
      - Wildcard patterns: ``*``, ``?`` and ``[...]`` in any part of the
        path, ``**`` for any depth.
      - GitHub repos via ``github://owner/repo`` or
        ``https://github.com/owner/repo`` (shallow clone of repo root),
        read like a local folder.
      - HTTP/HTTPS single files (follows redirects; expands archives **by
        extension**). The file is a ``SourceFile``: still a ``(name, bytes)``
        pair, plus ``.url`` (final address) and ``.warnings``; its name
        agrees with the server's Content-Type (a page at ``.../README.md``
        served as HTML becomes ``README.md.html``).

    Safety:
      - Archive expansion is capped (``MAX_ARCHIVE_EXPANSION_BYTES`` total
        uncompressed bytes, ``MAX_ARCHIVE_DEPTH`` nesting) to stop zip/tar
        bombs; exceeding a cap raises ``ValueError``.
      - With ``block_private_urls=True`` (default: the
        ``ATT_BLOCK_PRIVATE_URLS`` env var; the self-hosted server enables
        it per-request), HTTP(S) inputs — and their redirect targets — must
        resolve to public addresses (SSRF guard).
      - Links leading outside a folder are not followed.

    Extensibility:
      - Register new scheme/prefix handlers with
        ``register_unpack_handler(prefix, handler)``.
      - Or pass a one-off dict via `extra_handlers`.
    """
    return resolve(
        input,
        extra_handlers,
        block_private_urls=block_private_urls,
        options=options,
    ).files


__all__ = [
    "InvalidSourceOption",
    "Resolution",
    "SourceFile",
    "resolve",
    "unpack",
    "register_unpack_handler",
    "source",
    "extra_unpack_handlers",
]


# Import built-in source modules LAST so they can use the registry defined
# above (``from . import source`` / ``register_unpack_handler``) without a
# circular import — same layout as ``_processors/__init__.py``. New built-in
# source modules get their import line HERE, not in the top import block.
from ._file import SourceFile  # noqa: E402
from .archives import _explode_archive_bytes, _is_raw_archive_name  # noqa: E402, F401
from .github import (  # noqa: E402
    _clone_github_to_temp,
    _github_display_name,
    _is_github_repo_root_url,
)
from .http import _download_http_or_https  # noqa: E402
from .local import (  # noqa: E402
    InvalidSourceOption,
    TreeOptions,
    TreeReport,
    _looks_like_glob,
    read_archive,
    read_folder,
    read_pattern,
)

# Capture built-in source option schemas as defaults (additive, see
# _options.snapshot_option_defaults) so reset_options()/reset_processors()
# keeps them — even for modules that forget their own snapshot call.
snapshot_option_defaults()
