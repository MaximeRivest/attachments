"""Source resolution: turn an input string into ``(filename, bytes)`` pairs.

This package is the WHERE half of attachments (``_processors/`` is the
WHAT half). One module per source, mirroring the processor layout:

- ``local.py``    — single files + deterministic (sorted) directory walk
- ``archives.py`` — zip/tar expansion (recursive, bomb-guarded)
- ``http.py``     — http(s) single-file download (optional SSRF guard)
- ``github.py``   — ``github://owner/repo`` + github.com repo roots
- ``_guards.py``  — shared security machinery (expansion budget,
  member-name sanitization, SSRF guard, size caps)

Dispatch order in ``unpack()`` — preserved exactly, do not reorder:

1. Custom prefix handlers: global ``extra_unpack_handlers`` (filled by
   ``register_unpack_handler`` / ``@source``) updated with the per-call
   ``extra_handlers`` dict; the first matching prefix wins.
2. GitHub repo roots: ``github://...`` or ``https://github.com/owner/repo``
   (deeper github.com URLs fall through to plain HTTP download).
3. HTTP(S) URLs: single-file download; archives expanded by extension.
4. Local directory: deterministic recursive walk.
5. Local file: read as-is; archives expanded by extension.
6. Anything else raises ``ValueError``.

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

from collections.abc import Callable
from pathlib import Path

from .._options import snapshot_option_defaults

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


def unpack(
    input: str,
    extra_handlers: dict[str, Callable[[str], list[tuple[str, bytes]]]] | None = None,
    *,
    block_private_urls: bool | None = None,
) -> list[tuple[str, bytes]]:
    """Resolve an input path/spec into a flat list of ``(filename, bytes)``.

    Supported out-of-the-box:
      - Local directory (recursively walks, expands nested zips/tars by extension)
      - Local files (regular files; if ZIP/TAR, expands recursively)
      - ZIP files (.zip)
      - TAR archives (.tar, .tar.gz, .tgz, .tar.bz2, .tbz2, .tar.xz, .txz)
      - GitHub repos via ``github://owner/repo`` or
        ``https://github.com/owner/repo`` (shallow clone of repo root)
      - HTTP/HTTPS single files (follows redirects; expands archives **by extension**)

    Safety:
      - Archive expansion is capped (``MAX_ARCHIVE_EXPANSION_BYTES`` total
        uncompressed bytes, ``MAX_ARCHIVE_DEPTH`` nesting) to stop zip/tar
        bombs; exceeding a cap raises ``ValueError``.
      - With ``block_private_urls=True`` (default: the
        ``ATT_BLOCK_PRIVATE_URLS`` env var; the self-hosted server enables
        it per-request), HTTP(S) inputs — and their redirect targets — must
        resolve to public addresses (SSRF guard).

    Extensibility:
      - Register new scheme/prefix handlers with
        ``register_unpack_handler(prefix, handler)``.
      - Or pass a one-off dict via `extra_handlers`.
    """
    # Custom handlers (global then per-call)
    handlers = dict(extra_unpack_handlers)
    if extra_handlers:
        handlers.update(extra_handlers)
    for prefix, handler in handlers.items():
        if input.startswith(prefix):
            return handler(input)

    p = Path(input)

    # GitHub repo shorthand/scheme (repo root ONLY)
    if input.startswith("github://") or _is_github_repo_root_url(input):
        tmpdir = _clone_github_to_temp(input)
        try:
            return _walk_directory(tmpdir)
        finally:
            # We do NOT delete the temp dir here to allow downstream use
            pass

    # --- Added: HTTP/HTTPS single-file download ---
    if input.startswith("http://") or input.startswith("https://"):
        # If it's a GitHub URL but NOT a repo root, treat it as a file download
        name, data = _download_http_or_https(
            input, block_private_urls=block_private_urls
        )
        if _is_raw_archive_name(name):
            return _explode_archive_bytes(name, data)
        return [(name, data)]
    # --- end ---

    # Local directory
    if p.exists() and p.is_dir():
        return _walk_directory(p)

    # Local file
    if p.exists() and p.is_file():
        with open(p, "rb") as f:
            data = f.read()
        # Expand archives (by extension only)
        if _is_raw_archive_name(p.name):
            return _explode_archive_bytes(p.name, data)
        # Regular file -> as-is
        return [(p.name, data)]

    raise ValueError(f"Unsupported or non-existent input: {input}")


__all__ = [
    "unpack",
    "register_unpack_handler",
    "source",
    "extra_unpack_handlers",
]


# Import built-in source modules LAST so they can use the registry defined
# above (``from . import source`` / ``register_unpack_handler``) without a
# circular import — same layout as ``_processors/__init__.py``. New built-in
# source modules get their import line HERE, not in the top import block.
from .archives import _explode_archive_bytes, _is_raw_archive_name  # noqa: E402
from .github import _clone_github_to_temp, _is_github_repo_root_url  # noqa: E402
from .http import _download_http_or_https  # noqa: E402
from .local import _walk_directory  # noqa: E402

# Capture built-in source option schemas as defaults (additive, see
# _options.snapshot_option_defaults) so reset_options()/reset_processors()
# keeps them — even for modules that forget their own snapshot call.
snapshot_option_defaults()
