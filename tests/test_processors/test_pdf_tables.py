"""PDF text with PyMuPDF: tables as Markdown in place, pypdf as fallback."""

from __future__ import annotations

import sys

import pytest

from attachments import att
from attachments._processors.pdf import process_pdf

pymupdf = pytest.importorskip("pymupdf")

ROWS = [
    ["Item", "Qty", "Price"],
    ["Desk lamp", "2", "48.79"],
    ["Stapler", "12", "9.10"],
]


def _pdf_with_table(path=None, password=None) -> bytes:
    """Text, a ruled 3 x 3 table, more text."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 80), "Before the table.")
    x0, y0, w, h = 72, 120, 150, 24
    for r, row in enumerate(ROWS):
        for c, value in enumerate(row):
            cell = pymupdf.Rect(
                x0 + c * w, y0 + r * h, x0 + (c + 1) * w, y0 + (r + 1) * h
            )
            page.draw_rect(cell, color=(0, 0, 0), width=0.8)
            page.insert_text((cell.x0 + 4, cell.y1 - 7), value)
    page.insert_text((72, 260), "After the table.")
    if password:
        return doc.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw=password
        )
    return doc.tobytes()


def test_table_is_markdown_in_place():
    result = process_pdf(_pdf_with_table())
    text = result["text"]
    table = "| Item | Qty | Price |\n| --- | --- | --- |\n| Desk lamp | 2 | 48.79 |"
    assert table in text
    assert text.index("Before the table.") < text.index("| Item") < text.index("After")
    assert text.count("Desk lamp") == 1  # the table's text is not repeated
    extra = result["meta"]["extra"]
    assert extra["text_backend"] == "pymupdf" and extra["tables"] == 1


def test_tables_can_be_turned_off():
    result = process_pdf(_pdf_with_table(), tables=False)
    assert "| Item" not in result["text"] and "Desk lamp" in result["text"]
    assert "tables" not in result["meta"]["extra"]


def test_option_through_att(tmp_path):
    path = tmp_path / "invoice.pdf"
    path.write_bytes(_pdf_with_table())
    assert "| Item" not in att(f"{path}[tables: false]").text
    assert "| Item | Qty | Price |" in att(str(path)).text


def test_pages_and_segments():
    doc = pymupdf.open()
    for n in range(3):
        doc.new_page().insert_text((72, 72), f"Page {n + 1} text")
    result = process_pdf(doc.tobytes(), page_selection="1,3")
    text = result["text"]
    pages = {s["page"]: text[s["start"] : s["end"]] for s in result["meta"]["segments"]}
    assert pages == {1: "Page 1 text", 3: "Page 3 text"}


def test_password():
    data = _pdf_with_table(password="secret")
    assert process_pdf(data)["meta"]["error"]["code"] == "password-required"
    assert "| Item" in process_pdf(data, password="secret")["text"]


def test_pypdf_reads_when_pymupdf_is_missing(monkeypatch):
    pytest.importorskip("pypdf")
    data = _pdf_with_table()
    for name in ("pymupdf", "fitz"):
        monkeypatch.setitem(sys.modules, name, None)
    result = process_pdf(data, render_images=False)
    assert result["meta"]["extra"]["text_backend"] == "pypdf"
    assert "Desk lamp" in result["text"] and "| Item" not in result["text"]


def test_file_pymupdf_cannot_open_goes_to_pypdf(monkeypatch):
    pytest.importorskip("pypdf")
    from attachments._processors import pdf

    def broken(*args, **kwargs):
        return (None, None, 0, None, {"pymupdf_error": "cannot open"}, [])

    monkeypatch.setattr(pdf, "_extract_text_with_pymupdf", broken)
    result = process_pdf(_pdf_with_table(), render_images=False)
    extra = result["meta"]["extra"]
    assert extra["text_backend"] == "pypdf" and extra["pymupdf_error"] == "cannot open"
    assert "Desk lamp" in result["text"]
