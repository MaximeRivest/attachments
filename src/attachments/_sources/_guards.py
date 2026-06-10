"""Shared security machinery for source handlers.

Everything that keeps ``unpack()`` safe lives here: the archive
expansion budget (zip/tar-bomb guard), archive member-name sanitization
(path-traversal guard), HTTP download size caps, and the SSRF guard
that HTTP(S) downloads apply to URLs and every redirect target.

Contributor note: to add a new source, add one module in this package,
register it at import time (plus an import line in the block at the
BOTTOM of ``__init__.py`` — top-of-file imports run before the registry
exists and circular-import), and add tests — see DEVELOPMENT.md
("Building New Sources").
"""

from __future__ import annotations

import os
from urllib.request import HTTPRedirectHandler

# --- Added/changed for HTTP(S) support ---
# Configurable HTTP limits and UA (can be overridden via env)
MAX_HTTP_DOWNLOAD_BYTES = int(
    os.environ.get("ATT_MAX_DOWNLOAD_BYTES", str(256 * 1024 * 1024))
)
HTTP_USER_AGENT = os.environ.get(
    "ATT_USER_AGENT", "attachments-unpack/1.0 (+https://github.com/MaximeRivest/att)"
)
# --- end ---

# Decompression-bomb guards for archive expansion (overridable via env).
# MAX_ARCHIVE_EXPANSION_BYTES caps the TOTAL uncompressed bytes produced by
# expanding one archive (including nested archives); MAX_ARCHIVE_DEPTH caps
# archive-in-archive nesting. Both protect against zip/tar bombs: without
# them a few-hundred-KB upload could expand to many GB in memory.
MAX_ARCHIVE_EXPANSION_BYTES = int(
    os.environ.get("ATT_MAX_EXPANSION_BYTES", str(1024 * 1024 * 1024))
)
MAX_ARCHIVE_DEPTH = int(os.environ.get("ATT_MAX_ARCHIVE_DEPTH", "8"))

#: When true, HTTP(S) downloads refuse URLs that resolve to loopback,
#: link-local, or private-range addresses (SSRF guard). Off by default for
#: local/library use; the server enables it per-request (see server.py).
BLOCK_PRIVATE_URLS_DEFAULT = os.environ.get(
    "ATT_BLOCK_PRIVATE_URLS", ""
).strip().lower() in ("1", "true", "yes", "on")


def _sanitize_member_name(name: str) -> str:
    """Sanitize archive member name to prevent path traversal.

    Examples:
        >>> _sanitize_member_name("normal/path/file.txt")
        'normal/path/file.txt'
        >>> _sanitize_member_name("../../../etc/passwd")
        'etc/passwd'
        >>> _sanitize_member_name("/absolute/path.txt")
        'absolute/path.txt'
        >>> _sanitize_member_name("windows\\\\path\\\\file.txt")
        'windows/path/file.txt'
        >>> _sanitize_member_name("./current/./dir/file.txt")
        'current/dir/file.txt'
    """
    # Prevent path traversal from archives or remote names.
    name = name.replace("\\", "/")
    while name.startswith("/"):
        name = name[1:]
    parts = []
    for p in name.split("/"):
        if p in ("", ".", ".."):
            continue
        parts.append(p)
    return "/".join(parts)


def _read_member_capped(fp, virtual_name: str, budget: list[int]) -> bytes:
    """Read an archive member in chunks, charging a shared expansion budget.

    ``budget`` is a single-element list holding the remaining uncompressed
    bytes allowed for the whole expansion (shared across nested archives).
    Raises ``ValueError`` once the budget is exhausted, BEFORE buffering an
    unbounded amount of data — this is the zip/tar-bomb guard.
    """
    chunks: list[bytes] = []
    while True:
        chunk = fp.read(1024 * 1024)
        if not chunk:
            break
        budget[0] -= len(chunk)
        if budget[0] < 0:
            max_mb = MAX_ARCHIVE_EXPANSION_BYTES // (1024 * 1024)
            raise ValueError(
                f"Archive expansion exceeds the maximum total size "
                f"({max_mb} MB) at member {virtual_name!r}. "
                f"Raise ATT_MAX_EXPANSION_BYTES to override."
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _assert_public_http_url(url: str) -> None:
    """SSRF guard: reject URLs that do not resolve to public addresses.

    Raises ``ValueError`` when *url* is not plain http(s), has no hostname,
    cannot be resolved, or resolves to any non-global address (loopback,
    RFC1918 private ranges, link-local — including the 169.254.169.254
    cloud metadata endpoint — reserved, multicast, ...).
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"Blocked URL scheme {parsed.scheme!r} (only http/https allowed)"
        )
    host = parsed.hostname
    if not host:
        raise ValueError(f"Blocked URL without a hostname: {url}")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise ValueError(f"Cannot resolve host {host!r}: {e}") from e
    for info in infos:
        addr = str(info[4][0]).split("%", 1)[0]  # strip IPv6 zone id
        ip = ipaddress.ip_address(addr)
        if not ip.is_global:
            raise ValueError(
                f"Blocked URL {url!r}: host {host!r} resolves to "
                f"non-public address {ip}"
            )


class _ValidatingRedirectHandler(HTTPRedirectHandler):
    """Re-validate every redirect target against the SSRF guard."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        _assert_public_http_url(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)
