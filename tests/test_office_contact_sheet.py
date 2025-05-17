"""
test_office_contact_sheet.py
============================

Minimal, dependency-free unit tests covering the key paths in
`office_contact_sheet.py`.

The tests **monkey-patch** external-tool calls so they run anywhere,
even inside CI systems that lack MS Office / LibreOffice / pypdfium2.

Run with:
    python -m unittest test_office_contact_sheet.py
"""
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageFont

import attachments.office_contact_sheet as ocs

# ───────────────────────── Test helpers ──────────────────────────────────────
def _dummy_pages(n: int = 9, w: int = 200, h: int = 300):
    """Generate `n` simple Pillow images (white with centred numbers)."""
    font = ImageFont.load_default()
    for i in range(1, n + 1):
        img = Image.new("RGB", (w, h), "white")
        d = ImageDraw.Draw(img)
        text = str(i)
        tw, th = d.textbbox((0, 0), text, font=font)[2:]
        d.text(((w - tw) / 2, (h - th) / 2), text, fill="black", font=font)
        yield img


class _Monkey:
    """Context manager to temporarily monkey-patch module attributes."""
    def __init__(self, module, **replacements):
        self.module = module
        self.replacements = replacements
        self.backup = {}

    def __enter__(self):
        for k, v in self.replacements.items():
            self.backup[k] = getattr(self.module, k)
            setattr(self.module, k, v)

    def __exit__(self, exc_type, exc, tb):
        for k, v in self.backup.items():
            setattr(self.module, k, v)


# ───────────────────────────── Unit tests ────────────────────────────────────
class PdfContactSheetTest(unittest.TestCase):
    """pdf_to_contact_sheet behaviour with mocked pages."""

    def setUp(self):
        self.png_out = Path("tmp_contact.png")
        if self.png_out.exists():
            self.png_out.unlink()

    def tearDown(self):
        if self.png_out.exists():
            self.png_out.unlink()

    def test_creates_png_file(self):
        with _Monkey(ocs, _render_pages=lambda p, dpi=150: _dummy_pages()):
            ocs.pdf_to_contact_sheet("placeholder.pdf", self.png_out)
            self.assertTrue(self.png_out.exists())

    def test_grid_dimensions(self):
        with _Monkey(ocs, _render_pages=lambda p, dpi=150: _dummy_pages()):
            ocs.pdf_to_contact_sheet("placeholder.pdf", self.png_out)
            img = Image.open(self.png_out)
            first = next(_dummy_pages(1))
            expected = (first.width * 3, first.height * 3)
            self.assertEqual(img.size, expected)


class OfficePipelineTest(unittest.TestCase):
    """Full DOCX→PDF→PNG pipeline with both steps mocked."""

    def setUp(self):
        self.png_out = Path("tmp_office_contact.png")
        if self.png_out.exists():
            self.png_out.unlink()

    def tearDown(self):
        if self.png_out.exists():
            self.png_out.unlink()

    def test_office_file_to_contact_sheet(self):
        with _Monkey(
            ocs,
            office_to_pdf=lambda src, outdir=".": Path("placeholder.pdf"),
            _render_pages=lambda p, dpi=150: _dummy_pages(),
        ):
            out = ocs.office_file_to_contact_sheet("report.docx", self.png_out)
            self.assertTrue(Path(out).exists())


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2) 