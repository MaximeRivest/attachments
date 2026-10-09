# src/attachments/processors/pdf.py
from __future__ import annotations

import contextlib
import io
import logging
from dataclasses import dataclass
from typing import Any

from .._options import Option, register_options
from .._pages import (
    PagePicker,
    PageSelectionError,
    describe_pages,
    page_picker,
    parse_pages,
)
from ..types import (
    ERROR_INVALID_OPTION,
    ERROR_MISSING_DEPENDENCY,
    ERROR_PARSE,
    ERROR_PASSWORD_REQUIRED,
    ERROR_PROCESSING,
    error_artifact,
    make_artifact,
)
from . import register_processor
from ._imageout import (
    DEFAULT_QUALITY,
    check_image_output,
    limit,
    output_format,
    pil_encode,
)

_PAGE_SEPARATOR = "\n\n"

#: Default longest side of a rendered page image, in pixels. 200 dpi alone
#: gives 2200 px for a Letter page and 2667 px for a 16:9 slide, more than
#: models use: Claude shrinks anything over 1568 px, OpenAI anything over
#: 2048 px. 2000 also stays within Anthropic's per-image limit for requests
#: with more than 20 images (2000 x 2000), which a long PDF reaches.
#: ``max_dim: 0`` turns the cap off.
DEFAULT_MAX_DIM = 2000

#: ``image_format: auto`` (the default) draws a page as JPEG when pictures
#: (a scan, photos) cover at least this share of it, else as PNG. Measured
#: on scanned pages (evals/scans): PNG 2.3 MB a page, JPEG 0.38 MB, read
#: the same; on text and drawings PNG stays sharp and small.
PHOTO_COVER = 0.5

#: Pages ``ocr: auto`` reads at most in one document by default
#: (``configure(ocr_auto_pages=N)``); ``ocr: true`` reads them all, up to
#: ``ocr_max_pages`` when a server sets one. A page count, not a time limit,
#: so the same file always gives the same text. About a minute on a laptop.
AUTO_OCR_MAX_PAGES = 50


def _ocr_limit(forced: bool) -> tuple[int | None, str]:
    """Most pages OCR may read here, and how to say why it stopped."""
    from ..config import get_config

    hard = get_config("ocr_max_pages")
    auto = int(get_config("ocr_auto_pages") or AUTO_OCR_MAX_PAGES)
    if forced:
        return (
            (int(hard), "this machine reads at most that many") if hard else (None, "")
        )
    if hard and int(hard) < auto:
        return int(hard), "this machine reads at most that many"
    return auto, "automatic OCR stops there"


#: OCR draws pages at this resolution (at least): accurate down to 8 pt
#: print in the measurements, while lower resolutions start to slip.
OCR_DPI = 200

#: Longest side of a page drawn for OCR; larger pages (posters, plans) are
#: drawn smaller so one page cannot take gigabytes.
OCR_MAX_DIM = 4000

#: Note + extra.ocr_hint when a PDF has no text layer and rapidocr is
#: missing (ocr="auto"). Local remedy first, free hosted tier second;
#: kept under ~150 chars so the repr never clips the remedy.
SCANNED_PDF_HINT = (
    "No text layer (scanned?) - pip install attachments[ocr], "
    "or the free hosted tier: attachments.dev"
)


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
    page_texts: list[str], page_numbers: list[int]
) -> tuple[str, list[dict]]:
    """Join per-page texts and build page segments (IR contract: meta.segments).

    Each segment carries a 1-based page label, the 1-based ``page`` number
    (the same number as ``ImageItem.page`` on that page's render), and
    start/end offsets into the joined text.

    Examples:
        >>> text, segs = _join_pages_with_segments(["one", "two"], [1, 3])
        >>> text
        'one\\n\\ntwo'
        >>> segs[0]
        {'kind': 'page', 'label': 'page 1', 'start': 0, 'end': 3, 'page': 1}
        >>> segs[1]["page"], text[segs[1]["start"] : segs[1]["end"]]
        (3, 'two')
    """
    parts: list[str] = []
    segments: list[dict] = []
    offset = 0
    for page_number, page_text in zip(page_numbers, page_texts, strict=False):
        if parts:
            offset += len(_PAGE_SEPARATOR)
        segments.append(
            {
                "kind": "page",
                "label": f"page {page_number}",
                "start": offset,
                "end": offset + len(page_text),
                "page": page_number,
            }
        )
        parts.append(page_text)
        offset += len(page_text)
    return _PAGE_SEPARATOR.join(parts), segments


@_quiet_pdf_loggers()
def _extract_text_with_pypdf_or_pyPDF2(
    data: bytes,
    password: str | None,
    pick: PagePicker,
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
        indices = pick(total_pages)

        page_texts: list[str] = []
        parsed = 0
        for i in indices:
            try:
                page = reader.pages[i]
                t = page.extract_text() or ""
                parsed += 1
            except Exception:
                t = ""
            page_texts.append(t.strip())

        text, segments = _join_pages_with_segments(page_texts, [i + 1 for i in indices])
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
    pick: PagePicker,
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

        if total_pages is None:
            # pypdf failed too and the page count is unknown: a selection
            # (which may count from the end) cannot be resolved.
            extra["note"] = "pdfminer.six could not count the pages"
            return (None, None, 0, None, extra, [])
        indices = pick(total_pages)
        page_numbers = set(indices)

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
        text, segments = _join_pages_with_segments(page_texts, [i + 1 for i in indices])
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


def _open_pymupdf(data: bytes, password: str | None = None) -> Any:
    """A PyMuPDF document, unlocked with *password* when encrypted, or
    ``None`` when PyMuPDF is missing, fails, or the password is wrong."""
    try:
        try:  # PyMuPDF; its old module name `fitz` warns since 1.24
            import pymupdf as fitz
        except ImportError:
            import fitz
        doc = fitz.open(stream=data, filetype="pdf")
        if doc.needs_pass and not doc.authenticate(password or ""):
            doc.close()
            return None
        return doc
    except Exception:
        return None


def _image_cover(page: Any) -> float:
    """Share of the page (0-1) covered by pictures: a scan is ~1.

    Examples:
        >>> import pymupdf
        >>> doc = pymupdf.open()
        >>> _image_cover(doc.new_page())
        0.0
    """
    area = abs(page.rect)
    if not area:
        return 0.0
    covered = 0.0
    for info in page.get_image_info():
        box = page.rect & info["bbox"]
        if not box.is_empty:
            covered += abs(box)
    return min(1.0, covered / area)


def _is_blank(page: Any) -> bool:
    """No text, no pictures, no drawings: nothing to draw or read."""
    return (
        not page.get_text("text").strip()
        and not page.get_image_info()
        and not page.get_drawings()
    )


def _render_pages_with_pymupdf(
    data: bytes,
    pick: PagePicker,
    dpi: int,
    filename: str | None,
    *,
    max_dim: int | None = None,
    image_format: str = "png",
    quality: int = DEFAULT_QUALITY,
    password: str | None = None,
) -> tuple[list[dict], str | None, dict]:
    """Return (images, backend_name, extra).

    Each image is a dict with keys: name, mimetype, bytes, page. Pages are
    drawn at *dpi*, or smaller when that would exceed *max_dim* pixels on
    the longest side: the zoom is chosen so the page is drawn at the final
    size directly (sharper and faster than drawing large and shrinking).
    ``extra["downscaled_pages"]`` counts pages the cap made smaller.
    """
    extra: dict[str, Any] = {}
    try:
        try:  # PyMuPDF; its old module name `fitz` warns since 1.24
            import pymupdf as fitz
        except ImportError:
            import fitz

        auto = str(image_format).lower() == "auto"
        if not auto:
            _pil_format, mimetype, ext = output_format(image_format)
        cap = limit(max_dim)
        doc = fitz.open(stream=data, filetype="pdf")
        if doc.needs_pass:
            doc.authenticate(password or "")
        try:
            total = doc.page_count

            images: list[dict] = []
            downscaled = 0
            for i in pick(total):
                page = doc.load_page(i)
                zoom = dpi / 72.0
                longest = max(page.rect.width, page.rect.height)
                if cap and longest * zoom > cap:
                    zoom = cap / longest
                    downscaled += 1
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                if cap and max(pix.width, pix.height) > cap:  # pixel rounding
                    zoom *= (cap - 0.5) / max(pix.width, pix.height)
                    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                if auto:
                    photo = _image_cover(page) >= PHOTO_COVER
                    _pil_format, mimetype, ext = output_format(
                        "jpeg" if photo else "png"
                    )
                payload = (
                    pix.tobytes("jpg", jpg_quality=quality)
                    if mimetype == "image/jpeg"
                    else pix.tobytes("png")
                )
                images.append(
                    {
                        "name": f"{(filename or 'document')}-page-{i + 1}.{ext}",
                        "mimetype": mimetype,
                        "bytes": payload,
                        "page": i + 1,
                    }
                )
            extra["rendered_pages"] = len(images)
            extra["total_pages_seen"] = total
            if downscaled:
                extra["downscaled_pages"] = downscaled
            return images, "pymupdf", extra
        finally:
            doc.close()
    except Exception as e:
        extra["note"] = f"image rendering via PyMuPDF unavailable: {e}"
        return [], None, extra


def _render_pages_with_pdf2image(
    data: bytes,
    pick: PagePicker,
    dpi: int,
    filename: str | None,
    *,
    max_dim: int | None = None,
    image_format: str = "png",
    quality: int = DEFAULT_QUALITY,
) -> tuple[list[dict], str | None, dict]:
    """
    Fallback renderer using pdf2image (requires poppler on system).

    Same output and options as :func:`_render_pages_with_pymupdf`; pages
    over *max_dim* are shrunk with Pillow (which pdf2image depends on).
    """
    extra: dict[str, Any] = {}
    try:
        from pdf2image import convert_from_bytes
        from PIL import Image

        # Without PyMuPDF there is no page analysis: auto means PNG.
        auto = str(image_format).lower() == "auto"
        pil_format, mimetype, ext = output_format("png" if auto else image_format)
        cap = limit(max_dim)
        from pdf2image import pdfinfo_from_bytes

        total = int(pdfinfo_from_bytes(data)["Pages"])
        indices = pick(total)
        images: list[dict] = []
        downscaled = 0
        # One call per run of consecutive pages (pdf2image takes first/last).
        runs: list[list[int]] = []
        for i in indices:
            if runs and i == runs[-1][-1] + 1:
                runs[-1].append(i)
            else:
                runs.append([i])
        for run in runs:
            pil_pages = convert_from_bytes(
                data, dpi=dpi, first_page=run[0] + 1, last_page=run[-1] + 1, fmt="png"
            )
            for i, im in zip(run, pil_pages, strict=False):
                if cap and max(im.size) > cap:
                    im.thumbnail((cap, cap), Image.Resampling.LANCZOS)
                    downscaled += 1
                images.append(
                    {
                        "name": f"{(filename or 'document')}-page-{i + 1}.{ext}",
                        "mimetype": mimetype,
                        "bytes": pil_encode(im, pil_format, quality),
                        "page": i + 1,
                    }
                )
        extra["rendered_pages"] = len(images)
        if downscaled:
            extra["downscaled_pages"] = downscaled
        return images, "pdf2image", extra
    except Exception as e:
        extra["note"] = f"image rendering via pdf2image unavailable: {e}"
        return [], None, extra


@dataclass(frozen=True)
class _Picture:
    """A page drawn once for OCR, with what its delivered copy needs."""

    page: int  # 1-based
    image: Any  # Pillow RGB, at OCR resolution
    deliver: tuple[int, int] | None  # delivered size, None = not delivered
    photo: bool  # pictures cover most of it: JPEG under image_format auto


def _delivered_size(
    page: Any, dpi: int, max_dim: int | None
) -> tuple[tuple[int, int], bool]:
    """Pixel size of a delivered page picture, and whether max_dim shrank it.

    Exactly what :func:`_render_pages_with_pymupdf` would draw: the page at
    *dpi*, or smaller so the longest side is at most *max_dim*, with
    PyMuPDF's own rounding (the page box times the zoom, rounded outward).
    """
    import pymupdf as fitz

    def size(zoom: float) -> tuple[int, int]:
        box = (page.rect * fitz.Matrix(zoom, zoom)).irect
        return box.width, box.height

    cap = limit(max_dim)
    zoom = dpi / 72.0
    longest = max(page.rect.width, page.rect.height)
    shrunk = bool(cap and longest * zoom > cap)
    if shrunk:
        zoom = cap / longest
    width, height = size(zoom)
    if cap and max(width, height) > cap:  # pixel rounding, as the renderer
        zoom *= (cap - 0.5) / max(width, height)
        width, height = size(zoom)
    return (width, height), shrunk


def _page_drawer(
    data: bytes,
    doc: Any,
    dpi: int,
    *,
    deliver: set[int],
    images_dpi: int,
    max_dim: int | None,
) -> Any:
    """``draw(index)`` -> a :class:`_Picture` of that page, for OCR.

    Drawn at *dpi*, or smaller when the longest side would pass
    ``OCR_MAX_DIM``. Pages in *deliver* also get their delivered size, so
    the worker that reads the page can make its picture from the same
    drawing. PyMuPDF when it opened the document, else pdf2image (no page
    analysis there: pictures are PNG, at OCR size).
    """
    from PIL import Image

    if doc is not None:
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz

        def draw(index: int) -> _Picture:
            page = doc.load_page(index)
            zoom = dpi / 72.0
            longest = max(page.rect.width, page.rect.height) * zoom
            if longest > OCR_MAX_DIM:
                zoom *= OCR_MAX_DIM / longest
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            if pix.n != 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            size = None
            if index in deliver:
                size, _ = _delivered_size(page, images_dpi, max_dim)
            return _Picture(index + 1, image, size, _image_cover(page) >= PHOTO_COVER)

        return draw

    from pdf2image import convert_from_bytes

    def draw_pdf2image(index: int) -> _Picture:
        image = convert_from_bytes(
            data, dpi=dpi, first_page=index + 1, last_page=index + 1
        )[0]
        if max(image.size) > OCR_MAX_DIM:
            image.thumbnail((OCR_MAX_DIM, OCR_MAX_DIM))
        return _Picture(
            index + 1,
            image.convert("RGB"),
            image.size if index in deliver else None,
            False,
        )

    return draw_pdf2image


def _ocr_pages(
    data: bytes,
    doc: Any,
    pages: list[int],
    *,
    source: str,
    forced: bool,
    engine_name: str,
    dpi: int,
    extra: dict[str, Any],
    deliver: set[int],
    images_dpi: int,
    max_dim: int | None,
    image_format: str,
    quality: int,
    name_base: str,
) -> Any:
    """Read the text of *pages* (0-based) with OCR, several at once.

    Returns ``({page number: text}, [indices left unread], {page number:
    image})``. Pages in *deliver* get their picture made from the drawing
    OCR used, in the same worker thread (drawn once, compressed in
    parallel), turned upright when OCR had to turn the page to read it.
    Returns ``None`` when no engine is installed and OCR was automatic
    (the caller adds the install hint); an error artifact for a bad engine
    option, a failed engine, or forced OCR without an engine. Automatic
    OCR reads at most ``AUTO_OCR_MAX_PAGES`` pages; ``forced`` reads them
    all. Fills ``extra`` with ``ocr``, ``ocr_backend``, ``ocr_pages`` and,
    when a page had to be turned to be read, ``ocr_turned``.
    """
    from functools import partial
    from pathlib import PurePath

    from PIL import Image

    from ..deps import check_dep
    from ..types import missing_dep_artifact
    from . import _ocr
    from .image import LIGHTON_URL_ENV, LIGHTON_URL_UNSET_MSG, OCR_ENGINES, _lighton_url

    def error(code: str, message: str) -> dict:
        artifact = error_artifact(source, code, message)
        artifact["meta"]["kind"] = "pdf"
        return artifact

    engine = str(engine_name or "rapidocr").lower()
    if engine not in OCR_ENGINES:
        return error(
            ERROR_INVALID_OPTION,
            f"Unknown ocr_engine {engine_name!r} "
            f"(expected one of: {', '.join(OCR_ENGINES)})",
        )
    url: str | None = None
    if engine == "lighton":
        url = _lighton_url()
        if url is None:
            if forced:
                return error(ERROR_INVALID_OPTION, LIGHTON_URL_UNSET_MSG)
            engine = "rapidocr"  # ocr: auto falls back to the local engine
            extra["ocr_engine_fallback"] = "rapidocr"
    if engine == "rapidocr" and not check_dep("ocr").available:
        return missing_dep_artifact(source, "ocr") if forced else None

    most, _why = _ocr_limit(forced)
    chosen = pages if most is None else pages[:most]
    skipped = [] if most is None else pages[most:]
    recognize = (
        _ocr.lighton_reader(url) if url and engine == "lighton" else _ocr.recognize
    )
    upright = {
        90: Image.Transpose.ROTATE_270,  # clockwise quarter turn
        180: Image.Transpose.ROTATE_180,
        270: Image.Transpose.ROTATE_90,
    }

    def work(picture: _Picture) -> tuple[Any, dict | None]:
        read = recognize(picture.image)
        if picture.deliver is None:
            return read, None
        image = picture.image
        if image.size != picture.deliver:
            image = image.resize(picture.deliver, Image.Resampling.LANCZOS)
        if read.turned:
            image = image.transpose(upright[read.turned])
        fmt = str(image_format).lower()
        if fmt == "auto":
            fmt = "jpeg" if picture.photo else "png"
        pil_format, mimetype, ext = output_format(fmt)
        return read, {
            "name": f"{name_base}-page-{picture.page}.{ext}",
            "mimetype": mimetype,
            "bytes": pil_encode(image, pil_format, quality),
            "page": picture.page,
        }

    draw = _page_drawer(
        data, doc, dpi, deliver=deliver, images_dpi=images_dpi, max_dim=max_dim
    )
    try:
        results = _ocr.read_pages(
            ((i + 1, partial(draw, i)) for i in chosen),
            total=len(chosen),
            label=f"OCR {PurePath(source).name}",
            read=work,
            workers=4 if engine == "lighton" else None,  # remote: network-bound
        )
    except Exception as e:
        if engine == "lighton":
            return error(
                ERROR_PROCESSING,
                f"LightOn OCR request failed: {e}. Check that the vLLM endpoint "
                f"at {LIGHTON_URL_ENV} ({url}) is running and reachable.",
            )
        return error(ERROR_PROCESSING, f"OCR failed: {type(e).__name__}: {e}")
    extra["ocr"] = True
    extra["ocr_backend"] = engine
    extra["ocr_pages"] = sorted(results)
    turned = {str(n): r.turned for n, (r, _) in sorted(results.items()) if r.turned}
    if turned:
        extra["ocr_turned"] = turned
    texts = {n: r.text for n, (r, _) in results.items()}
    pictures = {n: image for n, (_, image) in results.items() if image is not None}
    return texts, skipped, pictures


def _describe(selection: Any, page_start: int, page_end: int | None) -> str:
    return describe_pages(
        {"page_selection": selection, "page_start": page_start, "page_end": page_end}
    )


def process_pdf(
    data: bytes,
    *,
    filename: str | None = None,
    # Text options
    password: str | None = None,
    page_start: int = 0,
    page_end: int | None = None,
    max_pages: int | None = None,
    page_selection: Any = None,
    # Image rendering options
    render_images: bool | str = "auto",  # False | True/"always" | "auto"
    images_dpi: int = 200,
    max_dim: int | None = DEFAULT_MAX_DIM,
    image_format: str = "auto",
    quality: int = DEFAULT_QUALITY,
    # OCR options
    ocr: bool | str = "auto",  # False | True/"always" | "auto"
    ocr_engine: str = "rapidocr",  # "rapidocr" | "lighton"
    **_opts: Any,
) -> dict:
    """
    PDF -> artifact dict with keys: text, images, audio, video, meta.

    Options (via att(..., **options)):
      - password: str | None         PDF password for encrypted docs.
      - page_start: int              0-based start page (default 0).
      - page_end: int | None         Stop BEFORE this 0-based page index.
      - page_selection:              Pages to read instead of the range:
                                     "1,3,5", "-1" (last), "-3-" (last
                                     three), "2-" ... (see attachments._pages;
                                     the ``pages`` option sets it).
      - max_pages: int | None        Hard cap on pages to parse/render.
      - render_images:               False | True/"always" | "auto"
                                     "auto" draws the pages that have no
                                     text layer (scans), blank ones aside.
      - images_dpi: int              Rendering resolution (default 200).
      - max_dim: int | None          Longest side of a page image in pixels
                                     (default 2000; 0 or None = no cap). The
                                     cap wins over images_dpi: a page that
                                     would be larger is drawn smaller.
      - image_format: str            "auto" (default): JPEG for a page that
                                     pictures (a scan, photos) cover at least
                                     half of, PNG for the rest; or "png"
                                     (lossless) or "jpeg" for every page.
      - quality: int                 JPEG quality 1-95 (default 85).
      - ocr:                         False | True/"always" | "auto"
                                     Page by page: OCR reads only pages
                                     whose text layer is empty (a text
                                     layer always wins), blank ones aside.
                                     "auto" reads up to AUTO_OCR_MAX_PAGES
                                     of them when rapidocr is installed
                                     (a warning names the rest), else
                                     records an ocr_hint; True reads them
                                     all, and with rapidocr missing returns
                                     the typed missing-dependency artifact;
                                     False never OCRs.
      - ocr_engine: str              "rapidocr" (local, default) or "lighton"
                                     (remote LightOnOCR vLLM endpoint, a
                                     SERVER capability configured via the
                                     ATTACHMENTS_LIGHTON_URL env var). With
                                     ocr="auto" and the env var unset, falls
                                     back to rapidocr silently
                                     (extra.ocr_engine_fallback); with forced
                                     OCR it is an invalid-option error.

    Dependencies:
      - Text: pypdf (preferred) or PyPDF2; fallback to pdfminer.six.
      - Images: PyMuPDF (fitz) preferred; fallback pdf2image (+poppler).
      - OCR: rapidocr + onnxruntime (pip install attachments[ocr]).
    """
    from ..deps import check_dep
    from ..types import missing_dep_artifact

    source = filename or "document.pdf"

    invalid = check_image_output(
        max_dim=max_dim, image_format=image_format, quality=quality, allow_auto=True
    )
    if invalid:
        artifact = error_artifact(source, ERROR_INVALID_OPTION, invalid)
        artifact["meta"]["kind"] = "pdf"
        return artifact

    selection = None
    if page_selection is not None:
        try:
            selection = parse_pages(page_selection)
        except PageSelectionError as e:
            artifact = error_artifact(source, ERROR_INVALID_OPTION, str(e))
            artifact["meta"]["kind"] = "pdf"
            return artifact
    pick = page_picker(page_start, page_end, max_pages, selection)

    def _render(
        dpi: int, *, delivered: bool, pages: PagePicker | None = None
    ) -> tuple[list[dict], str | None, dict]:
        """Render pages: PyMuPDF first, pdf2image as fallback.

        Delivered images follow the size/format options; *pages* narrows
        the selection (default: every selected page).
        """
        settings: dict[str, Any] = (
            {"max_dim": max_dim, "image_format": image_format, "quality": quality}
            if delivered
            else {"max_dim": None, "image_format": "png"}
        )
        args = (data, pages or pick, dpi, filename)
        imgs, backend, info = _render_pages_with_pymupdf(
            *args, **settings, password=password
        )
        if backend:
            return imgs, backend, {f"render_{k}": v for k, v in info.items()}
        imgs2, backend2, info2 = _render_pages_with_pdf2image(*args, **settings)
        merged = {f"render_{k}": v for k, v in info.items()}
        merged.update({f"render_fallback_{k}": v for k, v in info2.items()})
        return imgs2, backend2, merged

    # Typed missing-dependency signal: no text backend importable at all.
    if not (check_dep("pdf-text").available or check_dep("pdf-fallback").available):
        return missing_dep_artifact(source, "pdf")

    extra: dict[str, Any] = {}
    text: str = ""
    images: list[dict] = []
    segments: list[dict] = []

    # ---- TEXT extraction ----
    text1, total_pages, parsed_pages, backend1, extra1, segments1 = (
        _extract_text_with_pypdf_or_pyPDF2(data, password, pick)
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
            _extract_text_with_pdfminer(data, password, pick)
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
    if selection is not None:
        extra["page_selection"] = str(selection)
    asked = selection is not None or page_start or page_end is not None
    if asked and total_pages and not pick(int(total_pages)):
        # Nothing to read: say so, rather than "scanned PDF, try OCR".
        return make_artifact(
            meta={
                "kind": "pdf",
                "extra": extra,
                "warnings": [
                    f"pages: {_describe(selection, page_start, page_end)} "
                    f"selects no page of this {int(total_pages)}-page document"
                ],
            }
        )

    # ---- Pages: which to draw, which to read with OCR ----
    # Decided page by page: a scanned page inside a text PDF gets its
    # picture and its OCR like a fully scanned PDF does.
    ocr_note: str | None = None
    warnings: list[str] = []
    doc = _open_pymupdf(data, password)
    try:
        if total_pages is None and doc is not None:
            total_pages = doc.page_count
            extra["pages"] = int(total_pages)
        selected = pick(int(total_pages)) if total_pages else []
        page_text = {s["page"]: text[s["start"] : s["end"]] for s in segments}
        no_text = [i for i in selected if not page_text.get(i + 1, "").strip()]
        if doc is not None:
            # Blank pages have nothing to show or read.
            to_look_at = [i for i in no_text if not _is_blank(doc.load_page(i))]
        else:
            to_look_at = list(no_text)

        # ---- Which pages get a picture ----
        always = render_images is True or str(render_images).lower() == "always"
        if always:
            draw = list(selected)
        elif render_images is False or str(render_images).lower() == "false":
            draw = []
        else:  # auto: the pages a reader of the text alone would miss
            draw = list(to_look_at)

        # ---- OCR: pages without a text layer (a text layer always wins) ----
        # A page both read and pictured is drawn once: the OCR worker makes
        # its picture too.
        made: dict[int, dict] = {}
        ocr_forced = ocr is True or str(ocr).lower() == "always"
        ocr_auto = isinstance(ocr, str) and ocr.lower() == "auto"
        if to_look_at and (ocr_forced or ocr_auto):
            outcome = _ocr_pages(
                data,
                doc,
                to_look_at,
                source=source,
                forced=ocr_forced,
                engine_name=ocr_engine,
                dpi=max(int(images_dpi), OCR_DPI),
                extra=extra,
                deliver=set(draw),
                images_dpi=int(images_dpi),
                max_dim=max_dim,
                image_format=image_format,
                quality=quality,
                name_base=filename or "document",
            )
            if isinstance(outcome, dict):  # an error artifact
                outcome["meta"]["extra"] = extra
                return outcome
            if outcome is None:  # no engine: say how to get one
                extra["ocr_hint"] = SCANNED_PDF_HINT
                ocr_note = SCANNED_PDF_HINT
            else:
                read, skipped, made = outcome
                if skipped:
                    first = skipped[0] + 1
                    most, why = _ocr_limit(ocr_forced)
                    how = (
                        f"[pages: {first}-] reads the rest"
                        if ocr_forced
                        else f"[ocr: true] reads them all, [pages: {first}-] the rest"
                    )
                    warnings.append(
                        f"ocr: read the first {most} of {len(to_look_at)} pages "
                        f"without text ({why}); pages {first} and later have "
                        f"no text. {how}"
                    )
                if read:
                    texts = [
                        read.get(i + 1, page_text.get(i + 1, "")) for i in selected
                    ]
                    joined, joined_segments = _join_pages_with_segments(
                        texts, [i + 1 for i in selected]
                    )
                    if joined.strip():
                        text, segments = joined, joined_segments

        # ---- Page pictures not already made by OCR ----
        rest = {i for i in draw if i + 1 not in made}
        if rest:
            imgs, img_backend, extra_img = _render(
                int(images_dpi),
                delivered=True,
                pages=lambda total: [i for i in pick(total) if i in rest],
            )
            extra.update(extra_img)
            if img_backend:
                extra["image_backend"] = img_backend
                images = imgs
        if made:
            images = sorted([*images, *made.values()], key=lambda im: im["page"])
            extra.setdefault(
                "image_backend", "pymupdf" if doc is not None else "pdf2image"
            )
            extra["render_rendered_pages"] = len(images)
    finally:
        if doc is not None:
            doc.close()

    # Typed parse failure: every text backend errored out (not merely empty
    # output) and image rendering produced nothing either.
    if text1 is None and text2 is None and not images and not text.strip():
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
    if ocr_note:
        meta["note"] = ocr_note
    if warnings:
        meta["warnings"] = warnings
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
            help=(
                "Pages to read: 3, 2-5, 7- (to the end), 1,3,5, -1 (last), "
                "-3- (last three)"
            ),
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
            help=(
                "Pictures of pages: true/false, or auto (the pages with no text "
                "layer, such as scans)."
            ),
            example="images: true",
        ),
        Option(
            "dpi",
            "int",
            param="images_dpi",
            default=200,
            help="Resolution for rendered page images (max_dim caps the result).",
            example="dpi: 300",
        ),
        Option(
            "max_dim",
            "int",
            default=DEFAULT_MAX_DIM,
            help=(
                "Longest side of each page image in pixels, applied after dpi; "
                "0 = no cap."
            ),
            example="max_dim: 1568",
        ),
        Option(
            "image_format",
            "str",
            default="auto",
            help=(
                "auto (jpeg for scanned and photo pages, png for the rest), png "
                "(lossless, sharpest text) or jpeg (far smaller for scans)."
            ),
            example="image_format: jpeg",
        ),
        Option(
            "quality",
            "int",
            default=DEFAULT_QUALITY,
            help="JPEG quality, 1-95 (used with image_format: jpeg).",
            example="quality: 75",
        ),
        Option(
            "ocr",
            "bool_or_auto",
            default="auto",
            help=(
                "Read pages with no text layer (scans) with RapidOCR: true/false, "
                f"or auto (when rapidocr is installed; first {AUTO_OCR_MAX_PAGES} "
                "such pages)."
            ),
            example="ocr: true",
        ),
        Option(
            "ocr_engine",
            "str",
            default="rapidocr",
            help=(
                "OCR engine: rapidocr (local, default) or lighton (remote "
                "LightOnOCR vLLM endpoint via ATTACHMENTS_LIGHTON_URL)."
            ),
            example="ocr_engine: lighton",
        ),
        Option(
            "max_pages",
            "int",
            help="Hard cap on the number of pages parsed/rendered.",
            example="max_pages: 10",
        ),
    ),
)
