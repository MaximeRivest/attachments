# src/attachments/processors/pdf.py
from __future__ import annotations

import contextlib
import io
import logging
from typing import Any

from .._options import Option, register_options
from ..types import (
    ERROR_MISSING_DEPENDENCY,
    ERROR_PARSE,
    ERROR_PASSWORD_REQUIRED,
    error_artifact,
    make_artifact,
)
from . import register_processor

_PAGE_SEPARATOR = "\n\n"


@contextlib.contextmanager
def _quiet_pdf_loggers():
    """Silence pypdf/PyPDF2 console log spew while parsing.

    pypdf reports recoverable robustness fixes (e.g. ``EOF marker not
    found``, ``CAUTION: startxref ...``) by logging to the ``pypdf``
    logger, which — with no handlers configured — prints straight to
    stderr via logging's last-resort handler, with no filename context.
    ``att()`` reports problems in-band (error artifacts and ``meta``), so
    third-party log noise is suppressed for the duration of the parse and
    the previous logger levels are restored afterwards.

    Usable as a decorator (``contextlib`` context managers recreate
    themselves per call).
    """
    loggers = [logging.getLogger(name) for name in ("pypdf", "PyPDF2")]
    previous = [logger.level for logger in loggers]
    for logger in loggers:
        logger.setLevel(logging.CRITICAL + 1)
    try:
        yield
    finally:
        for logger, level in zip(loggers, previous, strict=True):
            logger.setLevel(level)


def _join_pages_with_segments(
    page_texts: list[str], first_page: int
) -> tuple[str, list[dict]]:
    """Join per-page texts and build page segments (IR contract: meta.segments).

    Each segment carries a 1-based page label and start/end offsets into the
    joined text.

    Examples:
        >>> text, segs = _join_pages_with_segments(["one", "two"], 0)
        >>> text
        'one\\n\\ntwo'
        >>> segs[0]
        {'kind': 'page', 'label': 'page 1', 'start': 0, 'end': 3}
        >>> text[segs[1]["start"] : segs[1]["end"]]
        'two'
    """
    parts: list[str] = []
    segments: list[dict] = []
    offset = 0
    for idx, page_text in enumerate(page_texts):
        if parts:
            offset += len(_PAGE_SEPARATOR)
        segments.append(
            {
                "kind": "page",
                "label": f"page {first_page + idx + 1}",
                "start": offset,
                "end": offset + len(page_text),
            }
        )
        parts.append(page_text)
        offset += len(page_text)
    return _PAGE_SEPARATOR.join(parts), segments


@_quiet_pdf_loggers()
def _extract_text_with_pypdf_or_pyPDF2(
    data: bytes,
    password: str | None,
    page_start: int,
    page_end: int | None,
    max_pages: int | None,
) -> tuple[str | None, int | None, int, str | None, dict, list[dict]]:
    """
    Returns (text, total_pages, parsed_pages, backend_name, extra, segments)
    If neither pypdf nor PyPDF2 is installed, returns
    (None, None, 0, None, {...}, []).
    """
    extra: dict[str, Any] = {}
    backend: str | None = None
    try:
        try:
            from pypdf import PdfReader  # preferred modern fork

            backend = "pypdf"
        except Exception:
            from PyPDF2 import PdfReader  # fallback

            backend = "PyPDF2"

        reader = PdfReader(io.BytesIO(data))
        encrypted = bool(getattr(reader, "is_encrypted", False))
        extra["encrypted"] = encrypted
        if encrypted:
            decrypted = False
            try:
                # Try provided password, else empty string
                result = reader.decrypt(password if password is not None else "")
                # pypdf returns a PasswordType IntEnum (NOT_DECRYPTED == 0);
                # PyPDF2 returns an int (0 == failure).
                decrypted = bool(result)
            except Exception as e:
                # A DependencyError here (e.g. AES needs `cryptography`) is a
                # missing-dependency situation, not a wrong password.
                if type(e).__name__ == "DependencyError":
                    raise
                extra["decrypt_error"] = str(e)
            if not decrypted:
                extra["password_required"] = True
                return (None, None, 0, backend, extra, [])

        total_pages = len(reader.pages)
        start = max(0, int(page_start or 0))
        stop = total_pages if page_end is None else min(int(page_end), total_pages)
        if max_pages is not None:
            stop = min(stop, start + int(max_pages))

        page_texts: list[str] = []
        parsed = 0
        for i in range(start, stop):
            try:
                page = reader.pages[i]
                t = page.extract_text() or ""
                parsed += 1
            except Exception:
                t = ""
            page_texts.append(t.strip())

        text, segments = _join_pages_with_segments(page_texts, start)
        return (text, total_pages, parsed, backend, extra, segments)
    except ImportError as e:
        # Neither pypdf nor PyPDF2 is installed
        extra["note"] = f"text extraction via pypdf/PyPDF2 unavailable: {e}"
        return (None, None, 0, None, extra, [])
    except Exception as e:
        # Typed detection (exception class check, never message matching):
        # pypdf raises DependencyError when an optional runtime dep is
        # missing (e.g. `cryptography` for AES-encrypted documents).
        if type(e).__name__ == "DependencyError":
            extra["dependency_error"] = str(e)
        else:
            extra["extract_error"] = str(e)
        extra["note"] = f"text extraction via pypdf/PyPDF2 unavailable: {e}"
        return (None, None, 0, None, extra, [])


def _extract_text_with_pdfminer(
    data: bytes,
    password: str | None,
    page_start: int,
    page_end: int | None,
    max_pages: int | None,
) -> tuple[str | None, int | None, int, str | None, dict, list[dict]]:
    """
    Returns (text, total_pages, parsed_pages, backend_name, extra, segments)
    If pdfminer.six isn't available, text is None.
    """
    extra: dict[str, Any] = {}
    try:
        from pdfminer.high_level import extract_text
        from pdfminer.pdfpage import PDFPage

        # Determine total pages (best-effort)
        try:
            total_pages = sum(
                1
                for _ in PDFPage.get_pages(
                    io.BytesIO(data),
                    password=password or "",
                    caching=True,
                    check_extractable=False,
                )
            )
        except Exception:
            total_pages = None

        start = max(0, int(page_start or 0))
        if page_end is None:
            stop = (
                total_pages if total_pages is not None else start + (max_pages or 10**9)
            )
        else:
            stop = (
                min(int(page_end), total_pages)
                if total_pages is not None
                else int(page_end)
            )

        if max_pages is not None:
            stop = min(stop, start + int(max_pages))

        page_numbers = set(range(start, stop))  # pdfminer expects 0-based indices

        raw = (
            extract_text(
                io.BytesIO(data),
                password=password or "",
                page_numbers=page_numbers if page_numbers else None,
            )
            or ""
        )
        # pdfminer terminates every page with a form feed; split on it to
        # recover page boundaries, dropping the artificial trailing piece.
        page_texts = [p.strip() for p in raw.split("\x0c")]
        if page_texts and page_texts[-1] == "":
            page_texts.pop()
        text, segments = _join_pages_with_segments(page_texts, start)
        parsed = len(page_texts)
        return (text, total_pages, parsed, "pdfminer.six", extra, segments)
    except ImportError as e:
        # pdfminer.six is not installed
        extra["note"] = f"text extraction via pdfminer.six unavailable: {e}"
        return (None, None, 0, None, extra, [])
    except Exception as e:
        # Typed detection of an encrypted document with a bad password
        # (exception class check — never error-message string matching).
        if type(e).__name__ == "PDFPasswordIncorrect":
            extra["password_required"] = True
        else:
            extra["extract_error"] = str(e)
        extra["note"] = f"text extraction via pdfminer.six unavailable: {e}"
        return (None, None, 0, None, extra, [])


def _render_pages_to_png_with_pymupdf(
    data: bytes,
    page_start: int,
    page_end: int | None,
    max_pages: int | None,
    dpi: int,
    filename: str | None,
) -> tuple[list[dict], str | None, dict]:
    """Return (images, backend_name, extra).

    Each image is a dict with keys: name, mimetype, bytes, page.
    """
    extra: dict[str, Any] = {}
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=data, filetype="pdf")
        try:
            total = doc.page_count
            start = max(0, int(page_start or 0))
            stop = total if page_end is None else min(int(page_end), total)
            if max_pages is not None:
                stop = min(stop, start + int(max_pages))
            scale = dpi / 72.0
            mat = fitz.Matrix(scale, scale)

            images: list[dict] = []
            for i in range(start, stop):
                page = doc.load_page(i)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                images.append(
                    {
                        "name": f"{(filename or 'document')}-page-{i + 1}.png",
                        "mimetype": "image/png",
                        "bytes": pix.tobytes("png"),
                        "page": i + 1,
                    }
                )
            extra["rendered_pages"] = len(images)
            extra["total_pages_seen"] = total
            return images, "pymupdf", extra
        finally:
            doc.close()
    except Exception as e:
        extra["note"] = f"image rendering via PyMuPDF unavailable: {e}"
        return [], None, extra


def _render_pages_to_png_with_pdf2image(
    data: bytes,
    page_start: int,
    page_end: int | None,
    max_pages: int | None,
    dpi: int,
    filename: str | None,
) -> tuple[list[dict], str | None, dict]:
    """
    Fallback renderer using pdf2image (requires poppler on system).
    """
    extra: dict[str, Any] = {}
    try:
        from pdf2image import convert_from_bytes

        start = max(0, int(page_start or 0))
        last = page_end
        if max_pages is not None:
            last = (
                (start + int(max_pages))
                if last is None
                else min(int(last), start + int(max_pages))
            )

        # pdf2image uses 1-based page indices
        pil_pages = convert_from_bytes(
            data,
            dpi=dpi,
            first_page=start + 1,
            last_page=(int(last) if last is not None else None),
            fmt="png",
        )
        images: list[dict] = []
        for idx, im in enumerate(pil_pages):
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            page_no = start + idx + 1
            images.append(
                {
                    "name": f"{(filename or 'document')}-page-{page_no}.png",
                    "mimetype": "image/png",
                    "bytes": buf.getvalue(),
                    "page": page_no,
                }
            )
        extra["rendered_pages"] = len(images)
        return images, "pdf2image", extra
    except Exception as e:
        extra["note"] = f"image rendering via pdf2image unavailable: {e}"
        return [], None, extra


def process_pdf(
    data: bytes,
    *,
    filename: str | None = None,
    # Text options
    password: str | None = None,
    page_start: int = 0,
    page_end: int | None = None,
    max_pages: int | None = None,
    # Image rendering options
    render_images: bool | str = "auto",  # False | True/"always" | "auto"
    images_dpi: int = 200,
    **_opts: Any,
) -> dict:
    """
    PDF -> artifact dict with keys: text, images, audio, video, meta.

    Options (via att(..., **options)):
      - password: str | None         PDF password for encrypted docs.
      - page_start: int              0-based start page (default 0).
      - page_end: int | None         Stop BEFORE this 0-based page index.
      - max_pages: int | None        Hard cap on pages to parse/render.
      - render_images:               False | True/"always" | "auto"
                                     "auto" renders only if text is empty.
      - images_dpi: int              PNG rendering resolution when rendering.

    Dependencies:
      - Text: pypdf (preferred) or PyPDF2; fallback to pdfminer.six.
      - Images: PyMuPDF (fitz) preferred; fallback pdf2image (+poppler).
    """
    from ..deps import check_dep
    from ..types import missing_dep_artifact

    source = filename or "document.pdf"

    # Typed missing-dependency signal: no text backend importable at all.
    if not (check_dep("pdf-text").available or check_dep("pdf-fallback").available):
        return missing_dep_artifact(source, "pdf")

    extra: dict[str, Any] = {}
    text: str = ""
    images: list[dict] = []
    segments: list[dict] = []

    # ---- TEXT extraction ----
    text1, total_pages, parsed_pages, backend1, extra1, segments1 = (
        _extract_text_with_pypdf_or_pyPDF2(
            data, password, page_start, page_end, max_pages
        )
    )
    extra.update(extra1)
    if backend1:
        extra["text_backend"] = backend1

    if extra.get("password_required"):
        artifact = error_artifact(
            source,
            ERROR_PASSWORD_REQUIRED,
            "PDF is encrypted and the password is missing or wrong. "
            "Provide it via password=... or [password: ...].",
        )
        artifact["meta"]["kind"] = "pdf"
        artifact["meta"]["extra"] = extra
        return artifact

    text2: str | None = None
    if text1 is None or text1.strip() == "":
        # fallback to pdfminer.six
        text2, total_pages2, parsed_pages2, backend2, extra2, segments2 = (
            _extract_text_with_pdfminer(data, password, page_start, page_end, max_pages)
        )
        extra.update({f"pdfminer_{k}": v for k, v in extra2.items()})
        if extra2.get("password_required"):
            artifact = error_artifact(
                source,
                ERROR_PASSWORD_REQUIRED,
                "PDF is encrypted and the password is missing or wrong. "
                "Provide it via password=... or [password: ...].",
            )
            artifact["meta"]["kind"] = "pdf"
            artifact["meta"]["extra"] = extra
            return artifact
        if backend2:
            extra["text_backend_fallback"] = backend2
        if total_pages is None and total_pages2 is not None:
            total_pages = total_pages2
        if parsed_pages == 0:
            parsed_pages = parsed_pages2
        text = text2 or ""
        segments = segments2 if text2 else []
    else:
        text = text1 or ""
        segments = segments1

    # Typed missing-dependency signal: a backend was importable but failed
    # because an optional runtime dep is missing (e.g. `cryptography` for
    # AES-encrypted PDFs). This must drive the service fallback in core.
    dep_detail = extra.get("dependency_error")
    if text1 is None and text2 is None and dep_detail:
        artifact = error_artifact(
            source,
            ERROR_MISSING_DEPENDENCY,
            f"PDF text extraction requires an optional dependency: "
            f"{dep_detail}. Install with: pip install cryptography",
        )
        artifact["meta"]["kind"] = "pdf"
        artifact["meta"]["extra"] = extra
        return artifact

    if total_pages is not None:
        extra["pages"] = int(total_pages)
    extra["parsed_pages"] = int(parsed_pages)

    # ---- IMAGE rendering (optional) ----
    def _should_render() -> bool:
        if render_images is True or str(render_images).lower() == "always":
            return True
        if render_images is False:
            return False
        # "auto" or anything else truthy -> only render if no text
        return text.strip() == ""

    if _should_render():
        imgs, img_backend, extra_img = _render_pages_to_png_with_pymupdf(
            data, page_start, page_end, max_pages, images_dpi, filename
        )
        extra.update({f"render_{k}": v for k, v in extra_img.items()})
        if img_backend:
            extra["image_backend"] = img_backend
            images = imgs
        else:
            # try pdf2image fallback
            imgs2, img_backend2, extra_img2 = _render_pages_to_png_with_pdf2image(
                data, page_start, page_end, max_pages, images_dpi, filename
            )
            extra.update({f"render_fallback_{k}": v for k, v in extra_img2.items()})
            if img_backend2:
                extra["image_backend"] = img_backend2
                images = imgs2

    # Typed parse failure: every text backend errored out (not merely empty
    # output) and image rendering produced nothing either.
    if text1 is None and text2 is None and not images:
        detail = (
            extra.get("extract_error")
            or extra.get("pdfminer_extract_error")
            or extra.get("note")
            or "no PDF backend could read the file"
        )
        artifact = error_artifact(source, ERROR_PARSE, f"Failed to parse PDF: {detail}")
        artifact["meta"]["kind"] = "pdf"
        artifact["meta"]["extra"] = extra
        return artifact

    # Final artifact
    meta: dict[str, Any] = {"kind": "pdf", "extra": extra}
    if segments:
        meta["segments"] = segments
    return make_artifact(
        text=text or "",
        images=images,  # list of {"name","mimetype","bytes","page"}
        meta=meta,
    )


register_processor(".pdf", process_pdf)
register_options(
    ".pdf",
    (
        Option(
            "pages",
            "pages",
            aliases=("page",),
            help="Pages to include: a 1-based page number or range.",
            example="pages: 1-4",
        ),
        Option(
            "password",
            "str",
            aliases=("pw",),
            help="Password for encrypted PDFs.",
            example="password: secret",
        ),
        Option(
            "images",
            "bool_or_auto",
            aliases=("render",),
            param="render_images",
            default="auto",
            help="Render pages to PNG: true/false, or auto (only when no text).",
            example="images: true",
        ),
        Option(
            "dpi",
            "int",
            param="images_dpi",
            default=200,
            help="Resolution for rendered page images.",
            example="dpi: 300",
        ),
        Option(
            "max_pages",
            "int",
            help="Hard cap on the number of pages parsed/rendered.",
            example="max_pages: 10",
        ),
    ),
)
