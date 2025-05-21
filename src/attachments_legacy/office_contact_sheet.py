"""
office_contact_sheet.py
=======================

Convert Word / PowerPoint / Excel files to PDF and build a 3 x 3 PNG
contact-sheet of the first nine pages (or fewer).

• Pure-Python dependencies are all permissive-licensed:
      Pillow (MIT)     - image manipulation
      pypdfium2 (Apache) - PDF rasterisation
      pywin32 (PSF)      - optional, only on Windows

• Document-to-PDF conversion delegates to one of:
      - MS Office COM automation (Windows only)
      - LibreOffice / soffice CLI
      - unoconv CLI
  These run **as external processes**, so any GPL/LGPL code they contain
  does *not* infect your project.

MIT Licence - do as you wish, just keep this header intact.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final, Iterable

from PIL import Image  # Pillow - MIT

# ──────────────────────────── PDF → thumbnails ──────────────────────────────
def _render_pages(pdf_path: Path, dpi: int = 150) -> Iterable[Image.Image]:
    """
    Yield each PDF page as a Pillow image at *dpi*.

    Requires *pypdfium2*  (Apache-2.0). Imported lazily so that simply
    importing this module doesn't hard-require the wheel at runtime.
    """
    try:
        import pypdfium2 as pdfium
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise ImportError(
            "pypdfium2 is needed to rasterise PDF pages. "
            "Install with:  pip install pypdfium2"
        ) from exc

    doc = pdfium.PdfDocument(str(pdf_path))
    for idx in range(len(doc)):
        page = doc[idx]
        pil_img = page.render(scale=dpi / 72).to_pil()
        yield pil_img
        page.close()
    doc.close()


def pdf_to_contact_sheet(
    pdf_path: str | Path,
    out_path: str | Path = "contact_sheet.png",
    cols: int = 3,
    rows: int = 3,
    dpi: int = 150,
) -> Path:
    """
    Rasterise the first *cols x rows* pages of *pdf_path* and write a PNG grid.

    Returns the output `Path`.
    """
    pdf_path = Path(pdf_path)
    out_path = Path(out_path)

    thumbs = []
    for image in _render_pages(pdf_path, dpi=dpi):
        thumbs.append(image)
        if len(thumbs) >= cols * rows:
            break

    if not thumbs:
        raise ValueError(f"{pdf_path} appears to contain no pages")

    # Normalise page size so the grid lines up perfectly
    w_max, h_max = max(i.width for i in thumbs), max(i.height for i in thumbs)
    thumbs = [i.resize((w_max, h_max), Image.Resampling.LANCZOS) for i in thumbs]

    sheet = Image.new("RGB", (cols * w_max, rows * h_max), "white")
    for idx, thumb in enumerate(thumbs):
        r, c = divmod(idx, cols)
        sheet.paste(thumb, (c * w_max, r * h_max))

    sheet.save(out_path)
    return out_path


# ──────────────────────────── Office → PDF back-ends ─────────────────────────
_OFFICE_EXTS: Final[set[str]] = {
    ".doc", ".docx",
    ".ppt", ".pptx",
    ".xls", ".xlsx",
}


def _convert_with_libreoffice(src: Path, outdir: Path) -> Path | None:  # pragma: no cover
    """LibreOffice / soffice CLI (Linux / macOS / Windows)."""
    soffice = shutil.which("libreoffice") or shutil.which("soffice")
    if not soffice:
        return None
    subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(outdir), str(src)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    pdf = outdir / (src.stem + ".pdf")
    return pdf if pdf.exists() else None


def _convert_with_unoconv(src: Path, outdir: Path) -> Path | None:  # pragma: no cover
    """unoconv CLI fallback (wraps LibreOffice)."""
    unoconv = shutil.which("unoconv")
    if not unoconv:
        return None
    subprocess.run(
        [unoconv, "-f", "pdf", "-o", str(outdir), str(src)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    pdf = outdir / (src.stem + ".pdf")
    return pdf if pdf.exists() else None


def office_to_pdf(src: str | Path, outdir: str | Path = ".") -> Path:
    """
    Convert *src* (Word / PowerPoint / Excel) to PDF.

    Tries back-ends in this order:
        1. LibreOffice / soffice
        2. unoconv

    Raises `RuntimeError` if none succeed.
    """
    src = Path(src).expanduser().resolve()
    outdir = Path(outdir).expanduser().resolve()

    if src.suffix.lower() not in _OFFICE_EXTS:
        raise ValueError(f"Unsupported extension: {src.suffix}")

    converters = (
        _convert_with_libreoffice,
        _convert_with_unoconv,
    )
    for conv in converters:
        try:
            pdf = conv(src, outdir)
            if pdf:
                return pdf
        except Exception as err:  # pragma: no cover
            print(f"[warn] {conv.__name__} failed: {err}", file=sys.stderr)

    raise RuntimeError(
        "Could not convert the document. Install LibreOffice/soffice or unoconv so that at least one back-end succeeds."
    )


# ──────────────────────────── Top-level convenience ─────────────────────────
def office_file_to_contact_sheet(
    input_path: str | Path,
    out_png: str | Path = "contact_sheet.png",
    temp_dir: str | Path = ".",
    dpi: int = 150,
) -> Path:
    """
    High-level one-liner:

        DOCX / PPTX / XLSX → PDF → 3 x 3 PNG grid → returns PNG Path
    """
    input_path = Path(input_path)
    temp_dir = Path(temp_dir)

    pdf_path = office_to_pdf(input_path, temp_dir)
    return pdf_to_contact_sheet(pdf_path, out_png, dpi=dpi)


# ────────────────────────────── CLI demo / manual test ───────────────────────
if __name__ == "__main__":  # pragma: no cover
    if len(sys.argv) < 2:
        print("Usage: python office_contact_sheet.py <document.(docx|pptx|xlsx)>")
        sys.exit(1)

    sheet = office_file_to_contact_sheet(sys.argv[1])
    print("Contact sheet saved →", sheet.resolve()) 