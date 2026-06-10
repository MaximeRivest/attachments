"""ZIP and TAR archive expansion (recursive, bomb-guarded).

Handles exploding raw archive blobs (``.zip``, ``.tar``, ``.tar.gz``,
...) into flat ``(virtual_path, bytes)`` lists, recursing into nested
archives by extension. Zip-based document formats (``.xlsx``,
``.docx``, ...) are deliberately NOT expanded. The expansion budget and
member-name sanitization live in ``_guards.py``.

Contributor note: to add a new source, add one module in this package,
register it at import time (plus an import line in the block at the
BOTTOM of ``__init__.py`` — top-of-file imports run before the registry
exists and circular-import), and add tests — see DEVELOPMENT.md
("Building New Sources").
"""

from __future__ import annotations

import io
import tarfile
import zipfile

from ._guards import (
    MAX_ARCHIVE_DEPTH,
    MAX_ARCHIVE_EXPANSION_BYTES,
    _read_member_capped,
    _sanitize_member_name,
)

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
