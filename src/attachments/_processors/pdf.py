# src/attachments/processors/pdf.py
from __future__ import annotations

import contextlib
import io
import logging
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


def _render_pages_with_pymupdf(
    data: bytes,
    pick: PagePicker,
    dpi: int,
    filename: str | None,
    *,
    max_dim: int | None = None,
    image_format: str = "png",
    quality: int = DEFAULT_QUALITY,
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

        _pil_format, mimetype, ext = output_format(image_format)
        jpeg = mimetype == "image/jpeg"
        cap = limit(max_dim)
        doc = fitz.open(stream=data, filetype="pdf")
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
                payload = (
                    pix.tobytes("jpg", jpg_quality=quality)
                    if jpeg
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

        pil_format, mimetype, ext = output_format(image_format)
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
    image_format: str = "png",
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
                                     "auto" renders only if text is empty.
      - images_dpi: int              Rendering resolution (default 200).
      - max_dim: int | None          Longest side of a page image in pixels
                                     (default 2000; 0 or None = no cap). The
                                     cap wins over images_dpi: a page that
                                     would be larger is drawn smaller.
      - image_format: str            "png" (default, lossless) or "jpeg".
      - quality: int                 JPEG quality 1-95 (default 85).
      - ocr:                         False | True/"always" | "auto"
                                     OCR runs ONLY when the extracted text
                                     layer is empty (a text layer always
                                     wins). "auto" OCRs scanned PDFs when
                                     rapidocr is installed, else records an
                                     ocr_hint; True with rapidocr missing
                                     returns the typed missing-dependency
                                     artifact; False never OCRs.
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
      - OCR: rapidocr_onnxruntime (pip install attachments[ocr]).
    """
    from ..deps import check_dep
    from ..types import missing_dep_artifact

    source = filename or "document.pdf"

    invalid = check_image_output(
        max_dim=max_dim, image_format=image_format, quality=quality
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

    def _render(dpi: int, *, delivered: bool) -> tuple[list[dict], str | None, dict]:
        """Render pages: PyMuPDF first, pdf2image as fallback.

        Delivered images follow the size/format options; OCR inputs
        (``delivered=False``) are full-size PNG, whatever the options.
        """
        settings: dict[str, Any] = (
            {"max_dim": max_dim, "image_format": image_format, "quality": quality}
            if delivered
            else {"max_dim": None, "image_format": "png"}
        )
        args = (data, pick, dpi, filename)
        imgs, backend, info = _render_pages_with_pymupdf(*args, **settings)
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

    # ---- IMAGE rendering (optional) ----
    def _should_render() -> bool:
        if render_images is True or str(render_images).lower() == "always":
            return True
        if render_images is False:
            return False
        # "auto" or anything else truthy -> only render if no text
        return text.strip() == ""

    # Whether the delivered page images are exactly what OCR wants (full
    # size, lossless); otherwise OCR renders its own copy below.
    images_full_quality = False
    if _should_render():
        imgs, img_backend, extra_img = _render(int(images_dpi), delivered=True)
        extra.update(extra_img)
        if img_backend:
            extra["image_backend"] = img_backend
            images = imgs
            images_full_quality = str(image_format).lower() == "png" and not (
                extra_img.get("render_downscaled_pages")
                or extra_img.get("render_fallback_downscaled_pages")
            )

    # ---- OCR (optional; only when there is no text layer) ----
    # A text layer always wins: OCR runs only when extracted text is empty.
    ocr_note: str | None = None
    ocr_forced = ocr is True or str(ocr).lower() == "always"
    ocr_auto = isinstance(ocr, str) and ocr.lower() == "auto"
    if text.strip() == "" and (ocr_forced or ocr_auto):
        from .image import (
            LIGHTON_URL_ENV,
            LIGHTON_URL_UNSET_MSG,
            OCR_ENGINES,
            _lighton_url,
            _ocr_image_bytes,
            _ocr_image_bytes_lighton,
        )

        def _ocr_error(code: str, message: str) -> dict:
            artifact = error_artifact(source, code, message)
            artifact["meta"]["kind"] = "pdf"
            artifact["meta"]["extra"] = extra
            return artifact

        # Engine dispatch: rapidocr (local, default) or lighton (remote).
        engine = str(ocr_engine or "rapidocr").lower()
        if engine not in OCR_ENGINES:
            return _ocr_error(
                ERROR_INVALID_OPTION,
                f"Unknown ocr_engine {ocr_engine!r} "
                f"(expected one of: {', '.join(OCR_ENGINES)})",
            )
        lighton_url: str | None = None
        if engine == "lighton":
            lighton_url = _lighton_url()
            if lighton_url is None:
                if ocr_forced:
                    return _ocr_error(ERROR_INVALID_OPTION, LIGHTON_URL_UNSET_MSG)
                # ocr=auto: fall back to the local engine silently.
                engine = "rapidocr"
                extra["ocr_engine_fallback"] = "rapidocr"

        if engine == "lighton" or check_dep("ocr").available:
            ocr_images = images if images_full_quality else []
            if not ocr_images:
                # Render pages just for OCR at an OCR-suitable resolution:
                # full size and lossless, whatever max_dim/image_format the
                # delivered images use (shrunk or JPEG pages OCR worse).
                ocr_dpi = max(int(images_dpi), 200)
                ocr_images, _backend, _ = _render(ocr_dpi, delivered=False)
            if ocr_images:
                ordered = sorted(ocr_images, key=lambda im: im["page"])
                if engine == "lighton":
                    try:
                        page_texts = [
                            _ocr_image_bytes_lighton(im["bytes"], url=lighton_url)
                            for im in ordered
                        ]
                    except Exception as e:
                        return _ocr_error(
                            ERROR_PROCESSING,
                            f"LightOn OCR request failed: {e}. Check that the "
                            f"vLLM endpoint at {LIGHTON_URL_ENV} ({lighton_url})"
                            f" is running and reachable.",
                        )
                else:
                    page_texts = [_ocr_image_bytes(im["bytes"]) for im in ordered]
                ocr_text, ocr_segments = _join_pages_with_segments(
                    page_texts, [im["page"] for im in ordered]
                )
                extra["ocr"] = True
                extra["ocr_backend"] = engine
                if ocr_text.strip():
                    text = ocr_text
                    segments = ocr_segments
        elif ocr_forced:
            # Forced OCR without rapidocr is a typed missing-dependency.
            return missing_dep_artifact(source, "ocr")
        else:
            # First-impression fix: never silently empty for scanned PDFs.
            # Kept under ~150 chars so the repr never clips the remedy.
            # Local remedy first, free hosted tier second (ocr is a HEAVY
            # install — the only place the service gets a mention).
            extra["ocr_hint"] = SCANNED_PDF_HINT
            ocr_note = SCANNED_PDF_HINT

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
            help="Render pages to images: true/false, or auto (only when no text).",
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
            default="png",
            help="png (lossless, best for text) or jpeg (far smaller for scans).",
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
                "OCR scanned pages with RapidOCR when there is no text layer: "
                "true/false, or auto (only when rapidocr is installed)."
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
