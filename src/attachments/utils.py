from __future__ import annotations

import io
import zipfile


def is_text_bytes(data: bytes) -> bool:
    """Heuristic to decide whether bytes are (mostly) text.
    - Reject if NUL bytes are present.
    - Otherwise, consider text if >= 95% of bytes are printable/control whitespace.
    """
    if not data:
        return True
    if b"\x00" in data:
        return False
    # Printable byte set + common control whitespace
    textchars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)))
    nontext = data.translate(None, textchars)
    return (len(nontext) / max(1, len(data))) < 0.05


#: OOXML container member prefix -> sniffed extension.
_OOXML_PREFIXES = (("word/", ".docx"), ("xl/", ".xlsx"), ("ppt/", ".pptx"))

#: HTML markers checked after stripping a UTF-8 BOM and leading whitespace.
_HTML_MARKERS = (b"<!doctype html", b"<html")


def _detect_zip_extension(data: bytes) -> str | None:
    """Discriminate OOXML containers from plain zip archives.

    OOXML files (docx/xlsx/pptx) are zips with a ``[Content_Types].xml``
    member plus a format-specific directory. Plain zips (and unreadable
    ones) return ``None`` — extracting archives is unpack's job, not a
    processor's.

    Examples:
        >>> import io, zipfile
        >>> buf = io.BytesIO()
        >>> with zipfile.ZipFile(buf, "w") as zf:
        ...     zf.writestr("[Content_Types].xml", "<Types/>")
        ...     zf.writestr("word/document.xml", "<doc/>")
        >>> _detect_zip_extension(buf.getvalue())
        '.docx'
        >>> _detect_zip_extension(b"PK\\x03\\x04 not really a zip")
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
    except Exception:
        return None
    if "[Content_Types].xml" not in names:
        return None
    for prefix, ext in _OOXML_PREFIXES:
        if any(name.startswith(prefix) for name in names):
            return ext
    return None


def detect_extension(data: bytes) -> str | None:
    """Sniff a file extension from magic bytes (content detection).

    Used by core routing when a filename's extension has no registered
    processor: the sniffed extension is looked up in the registry instead.
    Pure stdlib; returns ``None`` whenever the content is not confidently
    recognized.

    Recognized signatures:

    ========================  ==========
    Signature                 Extension
    ========================  ==========
    ``%PDF-``                 ``.pdf``
    ``\\x89PNG``               ``.png``
    ``\\xff\\xd8\\xff``          ``.jpg``
    ``GIF87a`` / ``GIF89a``   ``.gif``
    ``RIFF....WEBP``          ``.webp``
    ``BM`` + plausible size   ``.bmp``
    ``PK\\x03\\x04`` (OOXML)    ``.docx`` / ``.xlsx`` / ``.pptx``
    ``<!doctype html``/``<html``  ``.html``
    ========================  ==========

    Plain zip archives (no ``[Content_Types].xml``) return ``None`` —
    archives are unpack's job. Everything unrecognized returns ``None``.

    Examples:
        >>> detect_extension(b"%PDF-1.7 ...")
        '.pdf'
        >>> detect_extension(b"\\x89PNG\\r\\n\\x1a\\n...")
        '.png'
        >>> detect_extension(b"\\xff\\xd8\\xff\\xe0\\x00\\x10JFIF")
        '.jpg'
        >>> detect_extension(b"GIF87a...")
        '.gif'
        >>> detect_extension(b"GIF89a...")
        '.gif'
        >>> detect_extension(b"RIFF\\x12\\x00\\x00\\x00WEBPVP8 ")
        '.webp'

        BMP requires a plausible little-endian size field (bytes 2-6 equal
        to the actual length, or zero) so text starting with "BM" does not
        false-positive:

        >>> detect_extension(b"BM" + (30).to_bytes(4, "little") + b"\\x00" * 24)
        '.bmp'
        >>> detect_extension(b"BMW is a car maker, not a bitmap")

        OOXML zips are discriminated by their content types and layout;
        plain zips are left for unpack:

        >>> import io, zipfile
        >>> def make_zip(*names):
        ...     buf = io.BytesIO()
        ...     with zipfile.ZipFile(buf, "w") as zf:
        ...         for name in names:
        ...             zf.writestr(name, "x")
        ...     return buf.getvalue()
        >>> detect_extension(make_zip("[Content_Types].xml", "word/document.xml"))
        '.docx'
        >>> detect_extension(make_zip("[Content_Types].xml", "xl/workbook.xml"))
        '.xlsx'
        >>> detect_extension(make_zip("[Content_Types].xml", "ppt/presentation.xml"))
        '.pptx'
        >>> detect_extension(make_zip("hello.txt"))

        HTML is detected case-insensitively after stripping a UTF-8 BOM and
        leading whitespace:

        >>> detect_extension(b"  \\n\\t<!DOCTYPE HTML><html></html>")
        '.html'
        >>> detect_extension(b"\\xef\\xbb\\xbf<html lang='en'>")
        '.html'
        >>> detect_extension(b"<HTML><body/></HTML>")
        '.html'
        >>> detect_extension(b"<xml>not html</xml>")

        Everything else is unrecognized:

        >>> detect_extension(b"")
        >>> detect_extension(b"plain text content")
        >>> detect_extension(bytes(range(256)))
    """
    if data.startswith(b"%PDF-"):
        return ".pdf"
    if data.startswith(b"\x89PNG"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data.startswith(b"BM") and len(data) >= 26:
        declared_size = int.from_bytes(data[2:6], "little")
        if declared_size in (0, len(data)):
            return ".bmp"
    if data.startswith(b"PK\x03\x04"):
        return _detect_zip_extension(data)
    head = data
    if head.startswith(b"\xef\xbb\xbf"):
        head = head[3:]
    head = head.lstrip()[:256].lower()
    if head.startswith(_HTML_MARKERS):
        return ".html"
    return None


def guess_decode(data: bytes) -> tuple[str, str]:
    """Return (encoding, text) using a small, dependency-free strategy.
    Try utf-8, utf-8-sig, latin-1, cp1252, then utf-8 with 'replace' fallback.
    """
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            return enc, data.decode(enc)
        except UnicodeDecodeError:
            continue
    return "utf-8", data.decode("utf-8", "replace")
