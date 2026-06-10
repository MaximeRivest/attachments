"""HTTP(S) sources: single-file downloads.

Handles downloading one resource over http(s) — redirects followed,
filename taken from Content-Disposition or the URL path, size capped at
``MAX_HTTP_DOWNLOAD_BYTES``. With ``block_private_urls`` enabled, the
URL and every redirect target must pass the SSRF guard in
``_guards.py``. Archive expansion (by extension) happens in the
``unpack()`` dispatch (see ``__init__.py``).

Contributor note: to add a new source, add one module in this package,
register it at import time (plus an import line in the block at the
BOTTOM of ``__init__.py`` — top-of-file imports run before the registry
exists and circular-import), and add tests — see DEVELOPMENT.md
("Building New Sources").
"""

from __future__ import annotations

import io
import re

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


def _download_http_or_https(
    url: str, *, block_private_urls: bool | None = None
) -> tuple[str, bytes]:
    """Download a single HTTP(S) resource, returning (filename, bytes).

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

        # Fall back to URL path
        if not filename:
            # Use final URL after redirects if available
            final_url = resp.geturl() or url
            path = urlparse(final_url).path or urlparse(url).path
            filename = unquote(path.split("/")[-1]) or "download"

        filename = _sanitize_member_name(filename) or "download"

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

    return filename, buf.getvalue()
