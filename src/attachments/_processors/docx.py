"""Processor for Word documents (.docx).

Extracts text from paragraphs and tables. ``images: true`` adds a picture
of every page (drawn by LibreOffice, see ``_office_pages``);
``embedded_images: true`` adds the pictures stored in the file.
Requires ``python-docx``: ``pip install attachments[docx]``
"""

from __future__ import annotations

import logging
from typing import Any

from .._options import register_options
from ..types import ERROR_PARSE, error_artifact, make_artifact, missing_dep_artifact
from . import register_processor
from ._metadata import strip_metadata
from ._office_pages import (
    DEFAULT_DPI,
    DEFAULT_MAX_DIM,
    check_render_options,
    office_pictures,
    render_options,
    wants_pictures,
)

log = logging.getLogger("attachments.processors.docx")


def _extract_table_text(table) -> str:
    """Render a docx table as a simple pipe-delimited text table."""
    rows: list[str] = []
    for row in table.rows:
        cells = [cell.text.strip() for cell in row.cells]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def docx_processor(
    data: bytes,
    *,
    filename: str | None = None,
    render_images: bool | str = False,
    embedded_images: bool = False,
    dpi: int = DEFAULT_DPI,
    max_dim: int | None = DEFAULT_MAX_DIM,
    image_format: str = "auto",
    quality: int | None = None,
    _render_from: tuple[bytes, str] | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Convert .docx bytes to an artifact.

    Options:
        filename: Original filename (for metadata).
        render_images: (DSL ``images``) ``True``: a picture of every page,
            drawn by LibreOffice; ``"auto"``: only when LibreOffice is
            installed. Default ``False``.
        embedded_images: The pictures stored in the document. Default ``False``.
        dpi / max_dim / image_format / quality: page picture size and format,
            as for PDF page images.
        _render_from: ``(bytes, ext)`` to draw the pages from instead of
            *data* (``.doc``/``.odt`` read through a converted copy are drawn
            from the original).
    """
    filename = filename or "document.docx"
    extract_images = bool(embedded_images)
    mode = wants_pictures(render_images)
    if mode:
        invalid = check_render_options(
            source=filename,
            kind="document",
            dpi=dpi,
            max_dim=max_dim,
            image_format=image_format,
            quality=quality,
        )
        if invalid:
            return invalid

    try:
        from docx import Document
    except ImportError:
        return missing_dep_artifact(filename, "docx")

    import io

    try:
        doc = Document(io.BytesIO(data))
    except Exception as e:
        log.warning("failed to open docx %s: %s", filename, e)
        return error_artifact(
            filename, ERROR_PARSE, f"Failed to parse Word document: {e}"
        )

    # --- text extraction (paragraphs + tables in document order) ---
    parts: list[str] = []
    # Walk body elements to preserve paragraph/table ordering
    for element in doc.element.body:
        tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag
        if tag == "p":
            # Find matching paragraph object
            for para in doc.paragraphs:
                if para._element is element:
                    text = para.text.strip()
                    if text:
                        parts.append(text)
                    break
        elif tag == "tbl":
            for table in doc.tables:
                if table._element is element:
                    parts.append(_extract_table_text(table))
                    break

    full_text = "\n\n".join(parts)

    # --- image extraction ---
    images: list[dict[str, Any]] = []
    if extract_images:
        for i, rel in enumerate(doc.part.rels.values()):
            if "image" in rel.reltype:
                try:
                    img_part = rel.target_part
                    img_bytes = img_part.blob
                    ct = img_part.content_type or "image/png"
                    ext = ct.split("/")[-1].split("+")[0]
                    images.append(
                        {
                            "name": f"{filename}-image-{i + 1}.{ext}",
                            "mimetype": ct,
                            # No GPS, dates or camera serials to the model.
                            "bytes": strip_metadata(img_bytes, ct)[0],
                        }
                    )
                except Exception as exc:
                    log.debug("skipping image %d: %s", i, exc)

    extra: dict[str, Any] = {
        "filename": filename,
        "paragraphs": len(doc.paragraphs),
        "tables": len(doc.tables),
        "images_extracted": len(images),
    }
    meta: dict[str, Any] = {"kind": "document", "extra": extra}
    if mode:
        pictures = office_pictures(
            *(_render_from or (data, ".docx")),
            source=filename,
            kind="document",
            mode=mode,
            dpi=dpi,
            max_dim=max_dim,
            image_format=image_format,
            quality=quality or 85,
        )
        if isinstance(pictures, dict):  # an error artifact
            return pictures
        page_images, picture_extra, note = pictures
        images = page_images + images
        extra.update(picture_extra)
        if note:
            meta["note"] = note
    return make_artifact(text=full_text, images=images, meta=meta)


register_processor(".docx", docx_processor)
register_options(".docx", render_options(unit="page"))
