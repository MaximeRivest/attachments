"""HTTP(S) sources: single-file downloads.

Handles downloading one resource over http(s) — redirects followed,
filename taken from Content-Disposition or the URL path and made to agree
with the declared Content-Type, size capped at
``MAX_HTTP_DOWNLOAD_BYTES``. The result is a ``SourceFile`` carrying the
final URL, which core passes on (``meta.source``, the html ``url``
option). With ``block_private_urls`` enabled, the URL and every redirect
target must pass the SSRF guard in ``_guards.py``. Archive expansion (by
extension) happens in the ``unpack()`` dispatch (see ``__init__.py``).

Contributor note: to add a new source, add one module in this package,
register it at import time (plus an import line in the block at the
BOTTOM of ``__init__.py`` — top-of-file imports run before the registry
exists and circular-import), and add tests — see DEVELOPMENT.md
("Building New Sources").
"""

from __future__ import annotations

import io
import re

from ._file import SourceFile
from ._guards import (
    BLOCK_PRIVATE_URLS_DEFAULT,
    HTTP_USER_AGENT,
    MAX_HTTP_DOWNLOAD_BYTES,
    _assert_public_http_url,
    _sanitize_member_name,
    _ValidatingRedirectHandler,
)


def _filename_from_content_disposition(cd: str | None) -> str | None:
    """Best-effort extraction of filename from Content-Disposition.

    Examples:
        >>> _filename_from_content_disposition('attachment; filename="report.pdf"')
        'report.pdf'
        >>> _filename_from_content_disposition("attachment; filename=data.csv")
        'data.csv'
        >>> _filename_from_content_disposition(None)
        >>> _filename_from_content_disposition("")
    """
    if not cd:
        return None
    # RFC 5987: filename*=UTF-8''encoded%20name.ext
    m = re.search(r"filename\*\s*=\s*([^;]+)", cd, re.IGNORECASE)
    if m:
        val = m.group(1).strip().strip("\"'")
        # Split at "''" if present
        if "''" in val:
            _, _, val = val.partition("''")
        try:
            from urllib.parse import unquote

            return unquote(val)
        except Exception:
            return val

    # filename="name.ext"
    m = re.search(r"filename\s*=\s*([^;]+)", cd, re.IGNORECASE)
    if m:
        val = m.group(1).strip().strip("\"'")
        return val
    return None


#: Declared content type -> (extension to add, extensions that already agree).
#: Only types where the name's extension would send the bytes to the WRONG
#: processor are listed. Generic types (application/octet-stream,
#: text/plain, application/json, ...) never override a name: a ``.csv``
#: served as text/plain, or an ``.ipynb`` served as application/json, is
#: still what its name says.
_TYPE_EXTENSIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "text/html": (".html", (".html", ".htm", ".xhtml", ".xht", ".shtml")),
    "application/xhtml+xml": (".html", (".html", ".htm", ".xhtml", ".xht")),
    "application/pdf": (".pdf", (".pdf",)),
    "image/png": (".png", (".png",)),
    "image/jpeg": (".jpg", (".jpg", ".jpeg", ".jpe", ".jfif")),
    "image/gif": (".gif", (".gif",)),
    "image/webp": (".webp", (".webp",)),
    "image/svg+xml": (".svg", (".svg", ".svgz")),
    "text/csv": (".csv", (".csv",)),
}

#: Extensions of pages a server builds on request: HTML is what they are
#: expected to return, so serving HTML under them is not worth a warning.
_DYNAMIC_PAGE_EXTENSIONS = frozenset(
    {".php", ".asp", ".aspx", ".jsp", ".jspx", ".cgi", ".cfm", ".do",
     ".action", ".nsf"}
)  # fmt: skip

_REAL_EXTENSION = re.compile(r"\.[a-z][a-z0-9]{0,6}$", re.IGNORECASE)


def _name_for_content_type(
    name: str, content_type: str | None, url: str
) -> tuple[str, str | None]:
    """Make the filename agree with the type the server declared.

    Routing picks a processor from the file extension, so a GitHub page
    at ``.../blob/main/README.md`` (served as text/html) would otherwise
    be read as Markdown source and dump the page's raw HTML. When the
    declared type is specific and the extension disagrees, the matching
    extension is appended (``README.md.html``), as browsers do when they
    save a download. Returns ``(name, warning or None)``.

    Examples:
        >>> _name_for_content_type("README.md", "text/html; charset=utf-8", "u")[0]
        'README.md.html'
        >>> _name_for_content_type("1706.03762", "application/pdf", "u")
        ('1706.03762.pdf', None)
        >>> _name_for_content_type("data.csv", "text/plain", "u")
        ('data.csv', None)
        >>> _name_for_content_type("photo.JPEG", "image/jpeg", "u")
        ('photo.JPEG', None)
        >>> _name_for_content_type("index.php", "text/html", "u")
        ('index.php.html', None)
    """
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    entry = _TYPE_EXTENSIONS.get(mime)
    if entry is None:
        return name, None
    extension, agreeing = entry
    if name.lower().endswith(agreeing):
        return name, None
    old = _REAL_EXTENSION.search(name)
    renamed = name + extension
    if old is None or old.group(0).lower() in _DYNAMIC_PAGE_EXTENSIONS:
        return renamed, None
    kind = "a web page" if extension == ".html" else f"{extension[1:].upper()} data"
    warning = (
        f"The server sent {kind} ({mime}), not the {old.group(0)} file its "
        f"address suggests; it was read as {extension[1:].upper()}."
    )
    raw = _github_raw_url(url)
    if raw:
        warning += f" For the file itself, use {raw}"
    return renamed, warning


def _github_raw_url(url: str) -> str | None:
    """``raw.githubusercontent.com`` address for a github.com file page.

    Examples:
        >>> _github_raw_url("https://github.com/psf/requests/blob/main/README.md")
        'https://raw.githubusercontent.com/psf/requests/main/README.md'
        >>> _github_raw_url("https://example.com/a/b/blob/c") is None
        True
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.hostname not in ("github.com", "www.github.com"):
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 5 and parts[2] == "blob":
        owner, repo, _, ref, *rest = parts
        return (
            f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{'/'.join(rest)}"
        )
    return None


def _download_http_or_https(
    url: str, *, block_private_urls: bool | None = None
) -> SourceFile:
    """Download a single HTTP(S) resource as a ``SourceFile``.

    The result unpacks as ``(filename, bytes)``; it also carries the final
    URL (after redirects) and any warning about a name/type mismatch.

    The filename comes from Content-Disposition, else the last path
    segment of the final URL (``index`` for a bare ``/``), then agrees
    with the declared Content-Type (see ``_name_for_content_type``).

    With ``block_private_urls`` (default: ``BLOCK_PRIVATE_URLS_DEFAULT``,
    i.e. the ``ATT_BLOCK_PRIVATE_URLS`` env var), the URL — and every
    redirect target — must resolve to a public address (SSRF guard).
    """
    from urllib.parse import unquote, urlparse
    from urllib.request import Request, build_opener, urlopen

    if block_private_urls is None:
        block_private_urls = BLOCK_PRIVATE_URLS_DEFAULT

    req = Request(url, headers={"User-Agent": HTTP_USER_AGENT})

    if block_private_urls:
        _assert_public_http_url(url)

        opener = build_opener(_ValidatingRedirectHandler())
        resp_ctx = opener.open(req, timeout=60)
    else:
        resp_ctx = urlopen(req, timeout=60)

    with resp_ctx as resp:
        # Prefer filename from Content-Disposition
        filename = _filename_from_content_disposition(
            resp.headers.get("Content-Disposition")
        )

        final_url = resp.geturl() or url
        content_type = resp.headers.get("Content-Type")

        # Fall back to URL path (final URL after redirects)
        if not filename:
            path = urlparse(final_url).path or urlparse(url).path
            filename = unquote(path.split("/")[-1])
            if not filename:
                known = (content_type or "").split(";", 1)[0].strip().lower()
                filename = "index" if known in _TYPE_EXTENSIONS else "download"

        filename = _sanitize_member_name(filename) or "download"
        filename, warning = _name_for_content_type(filename, content_type, final_url)

        # Stream with size guard
        buf = io.BytesIO()
        total = 0
        chunk_size = 1024 * 1024  # 1 MiB
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_HTTP_DOWNLOAD_BYTES:
                max_mb = MAX_HTTP_DOWNLOAD_BYTES // (1024 * 1024)
                raise ValueError(f"Remote file exceeds max size ({max_mb} MB): {url}")
            buf.write(chunk)

    return SourceFile(
        filename,
        buf.getvalue(),
        url=final_url,
        warnings=(warning,) if warning else (),
    )
