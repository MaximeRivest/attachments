"""The text of PDF pages with PyMuPDF: reading order kept, tables as Markdown.

Text comes in the order the PDF stores it (PyMuPDF text blocks, not
re-sorted by position), which follows the author's columns more often than
a sort by position: measured on olmOCR-bench, it beat both pypdf (the
previous reader) and position sorting on multi-column pages and small
print (``evals/compare``). Ligatures are expanded ("ﬂuid" becomes "fluid"),
so the words can be searched.

Tables: PyMuPDF's table finder in its default mode, which needs the ruling
lines of a table. The looser mode (tables found from text alignment alone)
was rejected: it declared whole pages of prose and mathematics to be
tables. Each table found is written as a Markdown table where its first
text block was, and its text is not repeated. A merged cell repeats its
value in each column it spans (as the Word and web page readers do); the
first row is the header row. Tables with fewer than two rows or columns
are left as text.
"""

from __future__ import annotations

from typing import Any


def _flags(fitz: Any) -> int:
    # Not TEXT_PRESERVE_LIGATURES: expand ligatures. Not TEXT_PRESERVE_IMAGES:
    # no image blocks.
    return fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP


def table_markdown(rows: list[list[Any]]) -> str:
    """Rows of cell values (``None`` = covered by a merged cell) as Markdown.

    Examples:
        >>> print(table_markdown([["Item", "Qty"], ["Lamp", "2"], ["Pen", None]]))
        | Item | Qty |
        | --- | --- |
        | Lamp | 2 |
        | Pen | Pen |
        >>> print(table_markdown([["a|b", "x\\ny"], ["1", "2"]]))
        | a\\|b | x y |
        | --- | --- |
        | 1 | 2 |
        >>> table_markdown([["only one row", "x"]])
        ''
    """
    out: list[list[str]] = []
    for row in rows:
        cells: list[str] = []
        last = ""
        for value in row:
            text = last if value is None else " ".join(str(value).split())
            last = text
            cells.append(text.replace("|", "\\|"))
        out.append(cells)
    out = [r for r in out if any(r)] if len(out) > 1 else out
    if len(out) < 2 or max(len(r) for r in out) < 2:
        return ""
    width = max(len(r) for r in out)
    out = [r + [""] * (width - len(r)) for r in out]
    lines = ["| " + " | ".join(out[0]) + " |", "|" + " --- |" * width]
    lines += ["| " + " | ".join(r) + " |" for r in out[1:]]
    return "\n".join(lines)


def _tables(page: Any, fitz: Any) -> list[tuple[Any, str]]:
    """``[(box, markdown)]`` for the tables PyMuPDF finds on *page*."""
    found = []
    try:
        for table in page.find_tables().tables:
            markdown = table_markdown(table.extract())
            if markdown:
                found.append((fitz.Rect(table.bbox), markdown))
    except Exception:  # a page the table finder cannot handle: text only
        return []
    return found


def page_text(page: Any, fitz: Any, *, tables: bool = True) -> tuple[str, int]:
    """``(text, tables found)`` of one PyMuPDF page.

    Examples:
        >>> import pymupdf
        >>> doc = pymupdf.open()
        >>> page = doc.new_page()
        >>> _ = page.insert_text((72, 72), "First line")
        >>> page_text(page, pymupdf)
        ('First line', 0)
        >>> bool(_flags(pymupdf) & pymupdf.TEXT_PRESERVE_LIGATURES)  # expanded
        False
    """
    found = _tables(page, fitz) if tables else []
    parts: list[str] = []
    placed: set[int] = set()
    for x0, y0, x1, y1, text, _number, kind in page.get_text(
        "blocks", flags=_flags(fitz)
    ):
        if kind != 0:
            continue
        box = fitz.Rect(x0, y0, x1, y1)
        inside = None
        for i, (area, _md) in enumerate(found):
            if box.intersects(area) and (box & area).get_area() > 0.5 * max(
                box.get_area(), 1e-6
            ):
                inside = i
                break
        if inside is None:
            if text.strip():
                parts.append(text.strip())
        elif inside not in placed:
            placed.add(inside)
            parts.append(found[inside][1])
    parts += [md for i, (_area, md) in enumerate(found) if i not in placed]
    return "\n\n".join(parts), len(found)
