from __future__ import annotations

import io
import os
import re
import subprocess
import tarfile
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path

from ._options import Option, register_options, snapshot_option_defaults

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


# Only expand these "raw" archive formats.
# Avoid exploding zip-based formats like .xlsx/.docx.
RAW_ARCHIVE_SUFFIXES: tuple[str, ...] = (
    ".zip",
    ".tar",
    ".tgz",
    ".tar.gz",
    ".tbz2",
    ".tar.bz2",
    ".txz",
    ".tar.xz",
)


def _is_raw_archive_name(name: str) -> bool:
    """Check if filename is a raw archive that should be expanded.

    Examples:
        >>> _is_raw_archive_name("data.zip")
        True
        >>> _is_raw_archive_name("backup.tar.gz")
        True
        >>> _is_raw_archive_name("spreadsheet.xlsx")  # Not raw - zip-based format
        False
        >>> _is_raw_archive_name("document.docx")  # Not raw - zip-based format
        False
        >>> _is_raw_archive_name("archive.TGZ")  # Case insensitive
        True
    """
    lower = name.lower()
    return any(lower.endswith(suf) for suf in RAW_ARCHIVE_SUFFIXES)


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


def _is_zip_bytes(data: bytes) -> bool:
    """Check if data looks like a ZIP file (PK signature).

    Examples:
        >>> _is_zip_bytes(b"PK\\x03\\x04...")
        True
        >>> _is_zip_bytes(b"not a zip")
        False
        >>> _is_zip_bytes(b"")
        False
    """
    # PK signature
    return data[:2] == b"PK"


def _is_tar_bytes(data: bytes) -> bool:
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*"):
            return True
    except Exception:
        return False


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


def _explode_archive_bytes(
    container_name: str,
    data: bytes,
    _depth: int = 0,
    _budget: list[int] | None = None,
) -> list[tuple[str, bytes]]:
    """Expand a zip/tar bytes blob into a flat list of (virtual_path, bytes).
    Recurses into nested archives, but only if the inner name has a raw archive suffix.

    Decompression-bomb guards: the total uncompressed output is capped at
    ``MAX_ARCHIVE_EXPANSION_BYTES`` and nesting at ``MAX_ARCHIVE_DEPTH``;
    exceeding either raises ``ValueError`` (callers surface it as a typed
    ``unpack-error`` artifact / HTTP 400).
    """
    if _budget is None:
        _budget = [MAX_ARCHIVE_EXPANSION_BYTES]
    if _depth > MAX_ARCHIVE_DEPTH:
        raise ValueError(
            f"Archive nesting exceeds the maximum depth ({MAX_ARCHIVE_DEPTH}) "
            f"at {container_name!r}. Raise ATT_MAX_ARCHIVE_DEPTH to override."
        )

    out: list[tuple[str, bytes]] = []

    # ZIP
    if _is_zip_bytes(data):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for zi in zf.infolist():
                if zi.is_dir():
                    continue
                inner_name = _sanitize_member_name(zi.filename)
                virtual_name = (
                    f"{container_name}/{inner_name}" if container_name else inner_name
                )
                with zf.open(zi, "r") as fp:
                    inner = _read_member_capped(fp, virtual_name, _budget)
                if _is_raw_archive_name(inner_name) and (
                    _is_zip_bytes(inner) or _is_tar_bytes(inner)
                ):
                    out.extend(
                        _explode_archive_bytes(virtual_name, inner, _depth + 1, _budget)
                    )
                else:
                    out.append((virtual_name, inner))
        return out

    # TAR.*
    if _is_tar_bytes(data):
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
            for ti in tf.getmembers():
                if not ti.isreg():
                    continue
                inner_name = _sanitize_member_name(ti.name)
                fp = tf.extractfile(ti)
                if not fp:
                    continue
                virtual_name = (
                    f"{container_name}/{inner_name}" if container_name else inner_name
                )
                inner = _read_member_capped(fp, virtual_name, _budget)
                if _is_raw_archive_name(inner_name) and (
                    _is_zip_bytes(inner) or _is_tar_bytes(inner)
                ):
                    out.extend(
                        _explode_archive_bytes(virtual_name, inner, _depth + 1, _budget)
                    )
                else:
                    out.append((virtual_name, inner))
        return out

    # Not an archive; return as-is
    out.append((container_name or "blob", data))
    return out


def _walk_directory(path: Path) -> list[tuple[str, bytes]]:
    """Return ``(relative_path, bytes)`` for all files in a directory.

    Skips common VCS/cache directories like ``.git/`` by default.

    The walk is deterministic: directories and filenames are visited in
    sorted order, so artifact order — and therefore ``.text``, ``.chunk()``
    and the repr — never depends on filesystem internals or file-creation
    history (raw ``os.walk`` order varies across filesystems/machines,
    which would break prompt caching and reproducibility).
    """
    root = path.resolve()
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
        # Sort in place so os.walk descends in deterministic order.
        dirnames.sort()

        for fn in sorted(filenames):
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


_GITHUB_OWNER_REPO_RE = re.compile(
    r"^[a-zA-Z0-9][-a-zA-Z0-9_.]*[a-zA-Z0-9]?/[a-zA-Z0-9][-a-zA-Z0-9_.]*[a-zA-Z0-9]?(\.git)?$"
)

# Declared option schema for the built-in github:// source. The resolved
# `ref` is consumed by core._apply_source_options into a ?ref=... query
# parameter, which _clone_github_to_temp reads below.
register_options(
    "github://",
    (
        Option(
            "ref",
            "str",
            aliases=("branch", "tag"),
            help="Git branch, tag, or ref to clone.",
            example="ref: main",
        ),
    ),
)
snapshot_option_defaults()


def _validate_github_owner_repo(owner_repo: str) -> None:
    """Validate owner/repo format to prevent command injection."""
    # Must be exactly owner/repo format with safe characters
    if not _GITHUB_OWNER_REPO_RE.match(owner_repo):
        raise ValueError(f"Invalid GitHub owner/repo format: {owner_repo}")
    # Additional safety: no shell metacharacters or git options
    dangerous_patterns = ["--", "..", ";", "|", "&", "$", "`", "\n", "\r"]
    for pattern in dangerous_patterns:
        if pattern in owner_repo:
            raise ValueError(f"Invalid characters in GitHub spec: {owner_repo}")


def _clone_github_to_temp(spec: str) -> Path:
    """Clone a GitHub repository into a temporary directory.
    Supported forms:
      - github://owner/repo[?ref=branch_or_tag]
      - https://github.com/owner/repo[.git][?ref=...]
    Requires the `git` CLI to be available in PATH.

    Returns the path to the temporary directory.
    """
    import urllib.parse

    def parse(spec: str):
        if spec.startswith("github://"):
            rest = spec[len("github://") :]
            if "?" in rest:
                repo_path, qs = rest.split("?", 1)
                qs_dict = dict(urllib.parse.parse_qsl(qs))
            else:
                repo_path, qs_dict = rest, {}
            owner_repo = repo_path.strip("/")
            _validate_github_owner_repo(owner_repo)
            url = f"https://github.com/{owner_repo}.git"
            ref = qs_dict.get("ref")
            return url, ref
        if spec.startswith("https://github.com/"):
            u = urllib.parse.urlparse(spec)
            parts = [p for p in u.path.split("/") if p]
            # Only treat EXACT repo roots as cloneable: /owner/repo or /owner/repo.git
            if len(parts) != 2:
                raise ValueError("Unsupported GitHub spec")
            owner, repo = parts
            owner_repo = f"{owner}/{repo}"
            _validate_github_owner_repo(owner_repo)
            if not repo.endswith(".git"):
                repo = repo + ".git"
            ref = dict(urllib.parse.parse_qsl(u.query or "")).get("ref")
            url = f"https://github.com/{owner}/{repo}"
            return url, ref
        raise ValueError("Unsupported GitHub spec")

    url, ref = parse(spec)
    tmpdir = Path(tempfile.mkdtemp(prefix="attachments_github_"))
    # Shallow clone
    cmd = ["git", "clone", "--depth", "1"]
    if ref:
        cmd += ["--branch", ref]
    cmd += [url, str(tmpdir)]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except Exception as e:
        raise RuntimeError(f"git clone failed: {e}") from e

    return tmpdir


# --- Added for HTTP(S) support ---
def _is_github_repo_root_url(url: str) -> bool:
    """Return True if URL is exactly a GitHub repo root.

    Matches: owner/repo, owner/repo.git, with optional ?ref=...

    Examples:
        >>> _is_github_repo_root_url("https://github.com/owner/repo")
        True
        >>> _is_github_repo_root_url("https://github.com/owner/repo.git")
        True
        >>> _is_github_repo_root_url("https://github.com/owner/repo?ref=main")
        True
        >>> _is_github_repo_root_url("https://github.com/owner/repo/blob/main/file.py")
        False
        >>> _is_github_repo_root_url("https://example.com/owner/repo")
        False
    """
    if not url.startswith("https://github.com/"):
        return False
    from urllib.parse import urlparse

    parts = [p for p in urlparse(url).path.split("/") if p]
    return len(parts) == 2  # /owner/repo or /owner/repo.git


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


def _download_http_or_https(
    url: str, *, block_private_urls: bool | None = None
) -> tuple[str, bytes]:
    """Download a single HTTP(S) resource, returning (filename, bytes).

    With ``block_private_urls`` (default: ``BLOCK_PRIVATE_URLS_DEFAULT``,
    i.e. the ``ATT_BLOCK_PRIVATE_URLS`` env var), the URL — and every
    redirect target — must resolve to a public address (SSRF guard).
    """
    from urllib.parse import unquote, urlparse
    from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

    if block_private_urls is None:
        block_private_urls = BLOCK_PRIVATE_URLS_DEFAULT

    req = Request(url, headers={"User-Agent": HTTP_USER_AGENT})

    if block_private_urls:
        _assert_public_http_url(url)

        class _ValidatingRedirectHandler(HTTPRedirectHandler):
            """Re-validate every redirect target against the SSRF guard."""

            def redirect_request(self, request, fp, code, msg, headers, newurl):
                _assert_public_http_url(newurl)
                return super().redirect_request(request, fp, code, msg, headers, newurl)

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


# --- end HTTP(S) helpers ---


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
