"""Pictures of Office pages, slides and sheets (``images: true``).

LibreOffice prints the file to PDF; the PDF page renderer (PyMuPDF, else
pdf2image) draws the pages — the same sizes and formats as PDF page
images (``dpi``, ``max_dim``, ``image_format``, ``quality``).

What a picture shows, per kind of file:

- **Documents** (``.docx``, ``.doc``, ``.odt``): one picture per printed
  page, numbered ``page`` 1, 2, ... (the text has no page boundaries).
- **Presentations** (``.pptx``, ``.ppt``, ``.odp``): one picture per slide,
  hidden slides included, so picture N is slide N — the same number as
  the slide's text segment. LibreOffice leaves hidden slides out of a PDF
  unless told otherwise.
- **Spreadsheets** (``.xlsx``, ``.xls``, ``.ods``): one picture per sheet
  (LibreOffice's "whole sheet on one page" export), in workbook order,
  hidden sheets included — so picture N is sheet N, like the sheet
  segments. A large sheet becomes one tall picture shrunk to ``max_dim``;
  its data is in the text.

``images: true`` needs LibreOffice and a page renderer: without them the
result is a ``missing-dependency`` error (which lets a configured service
draw the pages). ``images: auto`` draws them when it can and otherwise
returns the text alone, with a note.
"""

from __future__ import annotations

import logging
from typing import Any

from .._options import Option
from .._pages import PagePicker
from ..deps import check_dep, find_libreoffice
from ..types import (
    ERROR_INVALID_OPTION,
    ERROR_PARSE,
    error_artifact,
    missing_dep_artifact,
)
from ._imageout import DEFAULT_QUALITY, check_image_output

log = logging.getLogger("attachments.processors.office_pages")

#: Office extension -> (LibreOffice PDF export filter, its settings, unit).
_FORMATS: dict[str, tuple[str, dict[str, Any], str]] = {
    ".docx": ("writer_pdf_Export", {}, "page"),
    ".doc": ("writer_pdf_Export", {}, "page"),
    ".odt": ("writer_pdf_Export", {}, "page"),
    ".pptx": ("impress_pdf_Export", {"ExportHiddenSlides": True}, "slide"),
    ".ppt": ("impress_pdf_Export", {"ExportHiddenSlides": True}, "slide"),
    ".odp": ("impress_pdf_Export", {"ExportHiddenSlides": True}, "slide"),
    ".xlsx": ("calc_pdf_Export", {"SinglePageSheets": True}, "sheet"),
    ".xls": ("calc_pdf_Export", {"SinglePageSheets": True}, "sheet"),
    ".ods": ("calc_pdf_Export", {"SinglePageSheets": True}, "sheet"),
}

DEFAULT_DPI = 200
DEFAULT_MAX_DIM = 2000

#: A page this small (in points) is an empty sheet: no picture for it.
_BLANK_POINTS = 2.0

NOTE_NO_LIBREOFFICE = (
    "Pages not drawn (images: auto): LibreOffice is not installed. "
    "images: true would say how to install it."
)


def render_options(*, unit: str, embedded: bool = True) -> tuple[Option, ...]:
    """The picture options, worded for pages, slides or sheets.

    ``embedded`` adds ``embedded_images`` (formats that can extract them).
    """
    options = (
        Option(
            "images",
            "bool_or_auto",
            aliases=("render",),
            param="render_images",
            default=False,
            help=(
                f"Pictures of each {unit}, drawn by LibreOffice: true/false, or "
                "auto (only when LibreOffice is installed)"
            ),
            example="images: true",
        ),
        Option(
            "dpi",
            "int",
            default=DEFAULT_DPI,
            help=f"Resolution of the {unit} pictures (max_dim caps the result)",
            example="dpi: 150",
        ),
        Option(
            "max_dim",
            "int",
            default=DEFAULT_MAX_DIM,
            help=f"Longest side of each {unit} picture in pixels; 0 = no cap",
            example="max_dim: 1568",
        ),
        Option(
            "image_format",
            "str",
            default="auto",
            help=(
                f"auto (jpeg for a {unit} that is mostly photos, png otherwise), "
                "png (sharpest text) or jpeg (smaller)"
            ),
            example="image_format: jpeg",
        ),
        Option(
            "quality",
            "int",
            default=DEFAULT_QUALITY,
            help="JPEG quality, 1-95 (used with image_format: jpeg)",
            example="quality: 75",
        ),
    )
    if not embedded:
        return options
    return (
        options[0],
        Option(
            "embedded_images",
            "bool",
            default=False,
            help="The pictures stored inside the file (photos, logos), as they are",
            example="embedded_images: true",
        ),
        *options[1:],
    )


def wants_pictures(render_images: Any) -> str | None:
    """``"always"``, ``"auto"`` or ``None`` for an ``images`` value."""
    if render_images is True or str(render_images).lower() in ("always", "true"):
        return "always"
    if isinstance(render_images, str) and render_images.lower() == "auto":
        return "auto"
    return None


def check_render_options(
    *, source: str, kind: str, dpi: Any, max_dim: Any, image_format: Any, quality: Any
) -> dict[str, Any] | None:
    """An ``invalid-option`` artifact for bad picture options, else ``None``."""
    problem = check_image_output(
        max_dim=max_dim, image_format=image_format, quality=quality, allow_auto=True
    )
    if problem is None and (
        isinstance(dpi, bool) or not isinstance(dpi, int) or not 10 <= dpi <= 1200
    ):
        problem = f"dpi must be an integer from 10 to 1200, got {dpi!r}"
    if problem is None:
        return None
    artifact = error_artifact(source, ERROR_INVALID_OPTION, problem)
    artifact["meta"]["kind"] = kind
    return artifact


def office_pictures(
    data: bytes,
    ext: str,
    *,
    source: str,
    kind: str,
    mode: str,
    pick: PagePicker | None = None,
    dpi: int = DEFAULT_DPI,
    max_dim: int | None = DEFAULT_MAX_DIM,
    image_format: str = "auto",
    quality: int = DEFAULT_QUALITY,
) -> tuple[list[dict[str, Any]], dict[str, Any], str | None] | dict[str, Any]:
    """Draw the pages of an Office file.

    Args:
        data: The file's bytes, in the format named by *ext*.
        mode: ``"always"`` (missing pieces are an error) or ``"auto"``.
        pick: Which pages, slides or sheets (0-based), given their count;
            ``None`` = all.

    Returns:
        ``(images, extra, note)``, or an error artifact (missing LibreOffice
        or renderer with ``mode="always"``, or a conversion failure).
    """
    from .legacy_office import ConversionError, convert
    from .pdf import _render_pages_with_pdf2image, _render_pages_with_pymupdf

    export_filter, settings, unit = _FORMATS[ext]
    soffice = find_libreoffice()
    has_renderer = check_dep("pdf-images").available or _has_pdf2image()
    if soffice is None or not has_renderer:
        if mode == "auto":
            note = (
                NOTE_NO_LIBREOFFICE
                if soffice is None
                else (
                    "Pages not drawn (images: auto): no PDF page renderer "
                    "(pip install pymupdf)."
                )
            )
            return [], {}, note
        artifact = missing_dep_artifact(
            source, "libreoffice" if soffice is None else "pdf-images"
        )
        artifact["meta"]["kind"] = kind
        return artifact

    try:
        pdf = convert(
            data,
            ext,
            ".pdf",
            soffice,
            export_filter=export_filter,
            filter_options=settings,
        )
    except (ConversionError, OSError) as e:
        log.warning("LibreOffice could not print %s: %s", source, e)
        artifact = error_artifact(
            source, ERROR_PARSE, f"Failed to draw the {unit}s of {source}: {e}"
        )
        artifact["meta"]["kind"] = kind
        return artifact

    blank = _blank_pages(pdf)

    def choose(total: int) -> list[int]:
        chosen = pick(total) if pick is not None else list(range(total))
        return [i for i in chosen if i not in blank]

    stem = source.rsplit("/", 1)[-1]
    args = (pdf, choose, dpi, f"{stem}-{unit}")
    settings_kw = {"max_dim": max_dim, "image_format": image_format, "quality": quality}
    images, backend, info = _render_pages_with_pymupdf(*args, **settings_kw)
    if not backend:
        images, backend, info = _render_pages_with_pdf2image(*args, **settings_kw)
    for image in images:  # "deck.pptx-slide-page-3.png" -> "deck.pptx-slide-3.png"
        image["name"] = image["name"].replace(f"-{unit}-page-", f"-{unit}-")
    extra = {
        "pictures": unit,
        "picture_renderer": f"libreoffice+{backend}" if backend else None,
    }
    if info.get("downscaled_pages"):
        extra["downscaled_pictures"] = info["downscaled_pages"]
    if blank:
        extra["blank_sheets"] = len(blank)
    return images, extra, None


def _has_pdf2image() -> bool:
    import importlib.util

    return importlib.util.find_spec("pdf2image") is not None


def _blank_pages(pdf: bytes) -> set[int]:
    """Pages LibreOffice prints for empty sheets (a point or two wide)."""
    try:
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
    except ImportError:
        return set()
    try:
        with fitz.open(stream=pdf, filetype="pdf") as doc:
            return {
                i
                for i, page in enumerate(doc)
                if page.rect.width <= _BLANK_POINTS
                and page.rect.height <= _BLANK_POINTS
            }
    except Exception:
        return set()
