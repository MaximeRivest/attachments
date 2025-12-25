# src/attachments/processors/pdf.py
from __future__ import annotations

import io
from typing import Any

from . import register_processor


def _extract_text_with_pypdf_or_pyPDF2(
    data: bytes,
    password: str | None,
    page_start: int,
    page_end: int | None,
    max_pages: int | None,
) -> tuple[str | None, int | None, int, str | None, dict]:
    """
    Returns (text, total_pages, parsed_pages, backend_name, meta_flags)
    If neither pypdf nor PyPDF2 is installed, returns (None, None, 0, None, {...}).
    """
    meta: dict[str, Any] = {}
    try:
        try:
            from pypdf import PdfReader  # preferred modern fork

            backend = "pypdf"
        except Exception:
            from PyPDF2 import PdfReader  # fallback

            backend = "PyPDF2"

        reader = PdfReader(io.BytesIO(data))
        encrypted = bool(getattr(reader, "is_encrypted", False))
        meta["encrypted"] = encrypted
        if encrypted:
            try:
                # Try provided password, else empty string
                if password is not None:
                    reader.decrypt(password)  # type: ignore[attr-defined]
                else:
                    reader.decrypt("")  # type: ignore[attr-defined]
            except Exception as e:
                meta["decrypt_error"] = str(e)

        total_pages = len(reader.pages)
        start = max(0, int(page_start or 0))
        stop = total_pages if page_end is None else min(int(page_end), total_pages)
        if max_pages is not None:
            stop = min(stop, start + int(max_pages))

        texts: list[str] = []
        parsed = 0
        for i in range(start, stop):
            try:
                page = reader.pages[i]
                t = page.extract_text() or ""
                texts.append(t)
                parsed += 1
            except Exception:
                texts.append("")

        return ("\n\n".join(texts).strip(), total_pages, parsed, backend, meta)
    except Exception as e:
        # Neither pypdf nor PyPDF2, or runtime error
        meta["note"] = f"text extraction via pypdf/PyPDF2 unavailable: {e}"
        return (None, None, 0, None, meta)


def _extract_text_with_pdfminer(
    data: bytes,
    password: str | None,
    page_start: int,
    page_end: int | None,
    max_pages: int | None,
) -> tuple[str | None, int | None, int, str | None, dict]:
    """
    Returns (text, total_pages, parsed_pages, backend_name, meta_flags)
    If pdfminer.six isn't available, text is None.
    """
    meta: dict[str, Any] = {}
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

        text = (
            extract_text(
                io.BytesIO(data),
                password=password or "",
                page_numbers=page_numbers if page_numbers else None,
            )
            or ""
        )
        parsed = max(0, stop - start)
        return (text.strip(), total_pages, parsed, "pdfminer.six", meta)
    except Exception as e:
        meta["note"] = f"text extraction via pdfminer.six unavailable: {e}"
        return (None, None, 0, None, meta)


def _render_pages_to_png_with_pymupdf(
    data: bytes,
    page_start: int,
    page_end: int | None,
    max_pages: int | None,
    dpi: int,
    filename: str | None,
) -> tuple[list[dict], str | None, dict]:
    """Return (images, backend_name, meta_flags).

    Each image is a dict with keys: name, mimetype, bytes, page.
    """
    meta: dict[str, Any] = {}
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
            meta["rendered_pages"] = len(images)
            meta["total_pages_seen"] = total
            return images, "pymupdf", meta
        finally:
            doc.close()
    except Exception as e:
        meta["note"] = f"image rendering via PyMuPDF unavailable: {e}"
        return [], None, meta


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
    meta: dict[str, Any] = {}
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
        meta["rendered_pages"] = len(images)
        return images, "pdf2image", meta
    except Exception as e:
        meta["note"] = f"image rendering via pdf2image unavailable: {e}"
        return [], None, meta


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
    PDF -> artifact dict with keys: text, images, audio, video, flags.

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
    flags: dict[str, Any] = {"type": "pdf"}
    text: str = ""
    images: list[dict] = []

    # ---- TEXT extraction ----
    text1, total_pages, parsed_pages, backend1, meta1 = (
        _extract_text_with_pypdf_or_pyPDF2(
            data, password, page_start, page_end, max_pages
        )
    )
    flags.update(meta1)
    if backend1:
        flags["text_backend"] = backend1

    if text1 is None or text1.strip() == "":
        # fallback to pdfminer.six
        text2, total_pages2, parsed_pages2, backend2, meta2 = (
            _extract_text_with_pdfminer(data, password, page_start, page_end, max_pages)
        )
        flags.update({f"pdfminer_{k}": v for k, v in meta2.items()})
        if backend2:
            flags["text_backend_fallback"] = backend2
        if total_pages is None and total_pages2 is not None:
            total_pages = total_pages2
        if parsed_pages == 0:
            parsed_pages = parsed_pages2
        text = text2 or ""
    else:
        text = text1 or ""

    if total_pages is not None:
        flags["pages"] = int(total_pages)
    flags["parsed_pages"] = int(parsed_pages)

    # ---- IMAGE rendering (optional) ----
    def _should_render() -> bool:
        if render_images is True or str(render_images).lower() == "always":
            return True
        if render_images is False:
            return False
        # "auto" or anything else truthy -> only render if no text
        return text.strip() == ""

    if _should_render():
        imgs, img_backend, meta_img = _render_pages_to_png_with_pymupdf(
            data, page_start, page_end, max_pages, images_dpi, filename
        )
        flags.update({f"render_{k}": v for k, v in meta_img.items()})
        if img_backend:
            flags["image_backend"] = img_backend
            images = imgs
        else:
            # try pdf2image fallback
            imgs2, img_backend2, meta_img2 = _render_pages_to_png_with_pdf2image(
                data, page_start, page_end, max_pages, images_dpi, filename
            )
            flags.update({f"render_fallback_{k}": v for k, v in meta_img2.items()})
            if img_backend2:
                flags["image_backend"] = img_backend2
                images = imgs2

    # Final artifact
    artifact = {
        "text": text or "",
        "images": images,  # list of {"name","mimetype","bytes","page"}
        "audio": [],
        "video": [],
        "flags": flags,
    }
    return artifact


register_processor(".pdf", process_pdf)
