"""The text of a Word document (.docx) as Markdown, from its XML.

Read straight from the file (standard library only), in document order:

- paragraphs; headings (``#`` by the style's heading level or outline
  level) and list items (``-``, or ``1.`` for numbered lists, indented by
  level);
- tables as Markdown tables: a header line, cells on one line (a cell's
  paragraphs joined with ``<br>``), merged cells handled (a cell merged
  down repeats its value, as HTML tables do here; one merged across fills
  its first column), nested tables flattened into their cell, and a
  one-cell table (a frame around content) read as the content it holds;
- what Word keeps in containers: content controls (``w:sdt``, common in
  templates and forms), custom XML, smart tags, and text boxes (after the
  paragraph that anchors them, read once: their duplicate legacy copy is
  skipped);
- inserted text of tracked changes (deleted text is left out), field
  results (not field codes), equations as their plain text.

Headers, footers, footnotes and comments are left out. Both the usual
("Transitional") and the "Strict" form of the format are read.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

_MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
_CONTAINERS = {"sdt", "sdtContent", "customXml", "smartTag", "ins", "moveTo"}


@dataclass
class _Doc:
    w: str  # "{namespace}" of the wordprocessing tags
    m: str  # "{namespace}" of the math tags
    headings: dict[str, int] = field(default_factory=dict)  # styleId -> level
    numbered: dict[tuple[str, str], bool] = field(default_factory=dict)
    paragraphs: int = 0
    tables: int = 0


def _ns(root: ET.Element) -> str:
    return root.tag[: root.tag.index("}") + 1] if root.tag.startswith("{") else ""


def _local(el: ET.Element) -> str:
    return el.tag.rsplit("}", 1)[-1]


def _styles(z: zipfile.ZipFile, d: _Doc) -> None:
    """Heading levels by style id, from names ("heading 2") or outline levels."""
    try:
        root = ET.fromstring(z.read("word/styles.xml"))
    except (KeyError, ET.ParseError):
        return
    w = d.w
    based: dict[str, str] = {}
    for style in root.iter(w + "style"):
        sid = style.get(w + "styleId") or ""
        name = (
            style.find(w + "name").get(w + "val")
            if style.find(w + "name") is not None
            else ""
        ).lower()
        outline = style.find(f"{w}pPr/{w}outlineLvl")
        match = re.fullmatch(r"heading (\d)", name)
        if match:
            d.headings[sid] = int(match.group(1))
        elif name == "title":
            d.headings[sid] = 1
        elif outline is not None and (outline.get(w + "val") or "").isdigit():
            level = int(outline.get(w + "val")) + 1
            if level <= 6:
                d.headings[sid] = level
        parent = style.find(w + "basedOn")
        if parent is not None:
            based[sid] = parent.get(w + "val") or ""
    for sid, parent in based.items():  # a style based on a heading is one
        seen = set()
        while sid not in d.headings and parent in based and parent not in seen:
            seen.add(parent)
            parent = based[parent]
        if sid not in d.headings and parent in d.headings:
            d.headings[sid] = d.headings[parent]


def _numbering(z: zipfile.ZipFile, d: _Doc) -> None:
    """Which (list id, level) pairs are numbered rather than bulleted."""
    try:
        root = ET.fromstring(z.read("word/numbering.xml"))
    except (KeyError, ET.ParseError):
        return
    w = d.w
    abstract: dict[str, dict[str, bool]] = {}
    for a in root.iter(w + "abstractNum"):
        levels = {}
        for lvl in a.iter(w + "lvl"):
            fmt = lvl.find(w + "numFmt")
            value = fmt.get(w + "val") if fmt is not None else "bullet"
            levels[lvl.get(w + "ilvl") or "0"] = value not in ("bullet", "none")
        abstract[a.get(w + "abstractNumId") or ""] = levels
    for num in root.iter(w + "num"):
        ref = num.find(w + "abstractNumId")
        levels = abstract.get(ref.get(w + "val") if ref is not None else "", {})
        for ilvl, numbered in levels.items():
            d.numbered[(num.get(w + "numId") or "", ilvl)] = numbered


def _children(el: ET.Element):
    """Direct children, looking through containers and alternate content."""
    for child in el:
        name = _local(child)
        if name in _CONTAINERS:
            yield from _children(child)
        elif child.tag == _MC + "AlternateContent":
            choice = child.find(_MC + "Choice")
            if choice is None:
                choice = child.find(_MC + "Fallback")
            if choice is not None:
                yield from _children(choice)
        else:
            yield child


def _runs_text(el: ET.Element, d: _Doc, boxes: list[ET.Element]) -> str:
    """Text of a paragraph's runs; text boxes are collected, not inlined."""
    w, out = d.w, []
    for child in el:
        tag = child.tag
        if tag == _MC + "Fallback":
            continue  # the legacy copy of what mc:Choice holds
        if tag == w + "t":
            out.append(child.text or "")
        elif tag in (w + "tab", w + "ptab"):
            out.append("\t")
        elif tag in (w + "br", w + "cr"):
            out.append("\n")
        elif tag == w + "noBreakHyphen":
            out.append("-")
        elif tag == d.m + "t":
            out.append(child.text or "")
        elif tag == w + "txbxContent":
            boxes.append(child)
        elif _local(child) in (
            "delText",
            "instrText",
            "del",
            "moveFrom",
            "footnoteReference",
        ):
            continue
        else:
            out.append(_runs_text(child, d, boxes))
    return "".join(out)


def _paragraph(p: ET.Element, d: _Doc, blocks: list[str]) -> None:
    w = d.w
    boxes: list[ET.Element] = []
    text = _runs_text(p, d, boxes)
    text = "\n".join(
        re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")
    ).strip()
    if text:
        d.paragraphs += 1
        props = p.find(w + "pPr")
        style = props.find(w + "pStyle") if props is not None else None
        level = (
            d.headings.get(style.get(w + "val") or "") if style is not None else None
        )
        outline = props.find(w + "outlineLvl") if props is not None else None
        if (
            level is None
            and outline is not None
            and (outline.get(w + "val") or "").isdigit()
        ):
            level = (
                int(outline.get(w + "val")) + 1
                if int(outline.get(w + "val")) < 6
                else None
            )
        num = props.find(w + "numPr") if props is not None else None
        if level:
            text = "#" * level + " " + text.replace("\n", " ")
        elif num is not None and num.find(w + "numId") is not None:
            num_id = num.find(w + "numId").get(w + "val") or ""
            ilvl_el = num.find(w + "ilvl")
            ilvl = ilvl_el.get(w + "val") if ilvl_el is not None else "0"
            if num_id != "0":  # numId 0 switches numbering off
                marker = "1." if d.numbered.get((num_id, ilvl or "0")) else "-"
                indent = "  " * int(ilvl or "0")
                text = indent + marker + " " + text.replace("\n", " ")
        blocks.append(text)
    for box in boxes:
        _blocks(box, d, blocks)


def _cell_text(tc: ET.Element, d: _Doc) -> str:
    parts: list[str] = []
    _blocks(tc, d, parts, in_table=True)
    text = "<br>".join(p.replace("\n", "<br>") for p in parts if p)
    return text.replace("|", "\\|")


def _table(tbl: ET.Element, d: _Doc, blocks: list[str]) -> None:
    w = d.w
    rows_el = [c for c in _children(tbl) if c.tag == w + "tr"]
    cells_el = [c for r in rows_el for c in _children(r) if c.tag == w + "tc"]
    if len(cells_el) == 1:  # a one-cell table is a frame: read what it holds
        _blocks(cells_el[0], d, blocks)
        return
    grid: list[list[str]] = []
    above: dict[int, str] = {}  # column -> text of the cell a merge continues
    for tr in (c for c in _children(tbl) if c.tag == w + "tr"):
        row: list[str] = []
        props = tr.find(w + "trPr")
        before = props.find(w + "gridBefore") if props is not None else None
        if before is not None and (before.get(w + "val") or "").isdigit():
            row.extend([""] * int(before.get(w + "val")))
        for tc in (c for c in _children(tr) if c.tag == w + "tc"):
            pr = tc.find(w + "tcPr")
            span_el = pr.find(w + "gridSpan") if pr is not None else None
            span = (
                int(span_el.get(w + "val"))
                if span_el is not None and (span_el.get(w + "val") or "").isdigit()
                else 1
            )
            merge = pr.find(w + "vMerge") if pr is not None else None
            column = len(row)
            if merge is not None and merge.get(w + "val") not in ("restart",):
                text = above.get(column, "")
            else:
                text = _cell_text(tc, d)
            above[column] = text
            row.append(text)
            row.extend([""] * (span - 1))
        if any(cell.strip() for cell in row):
            grid.append(row)
    if not grid:
        return
    d.tables += 1
    width = max(len(r) for r in grid)
    rows = [r + [""] * (width - len(r)) for r in grid]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * width]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    blocks.append("\n".join(lines))


def _blocks(
    parent: ET.Element, d: _Doc, blocks: list[str], in_table: bool = False
) -> None:
    w = d.w
    for child in _children(parent):
        if child.tag == w + "p":
            _paragraph(child, d, blocks)
        elif child.tag == w + "tbl":
            if in_table:  # a nested table: its cells' text, row by row
                inner: list[str] = []
                for tr in (c for c in _children(child) if c.tag == w + "tr"):
                    cells = [
                        _cell_text(tc, d) for tc in _children(tr) if tc.tag == w + "tc"
                    ]
                    inner.append(" ".join(c for c in cells if c))
                blocks.extend(x for x in inner if x)
            else:
                _table(child, d, blocks)


def docx_markdown(data: bytes) -> tuple[str, dict[str, int]]:
    """``(markdown, {"paragraphs": n, "tables": n})`` of a .docx file.

    Raises ``ValueError`` when the bytes are not a readable Word document.

    Examples:
        >>> import io, zipfile
        >>> W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        >>> body = (
        ...     "<w:p><w:r><w:t>Hello</w:t></w:r></w:p>"
        ...     "<w:sdt><w:sdtContent><w:tbl>"
        ...     "<w:tr><w:tc><w:p><w:r><w:t>a</w:t></w:r></w:p></w:tc>"
        ...     "<w:tc><w:p><w:r><w:t>b</w:t></w:r></w:p></w:tc></w:tr>"
        ...     "<w:tr><w:tc><w:p><w:r><w:t>1</w:t></w:r></w:p>"
        ...     "<w:p><w:r><w:t>one</w:t></w:r></w:p></w:tc>"
        ...     "<w:tc><w:p><w:r><w:t>2 | 3</w:t></w:r></w:p></w:tc></w:tr>"
        ...     "</w:tbl></w:sdtContent></w:sdt>"
        ... )
        >>> xml = f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>'
        >>> buffer = io.BytesIO()
        >>> with zipfile.ZipFile(buffer, "w") as z:
        ...     z.writestr("word/document.xml", xml)
        >>> text, stats = docx_markdown(buffer.getvalue())
        >>> print(text)
        Hello
        <BLANKLINE>
        | a | b |
        | --- | --- |
        | 1<br>one | 2 \\| 3 |
        >>> stats
        {'paragraphs': 6, 'tables': 1}
    """
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        root = ET.fromstring(z.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        raise ValueError(f"not a readable Word document: {e}") from e
    w = _ns(root)
    strict = "purl.oclc.org" in w
    m = (
        "{http://purl.oclc.org/ooxml/officeDocument/math}"
        if strict
        else "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
    )
    d = _Doc(w=w, m=m)
    _styles(z, d)
    _numbering(z, d)
    body = root.find(w + "body")
    blocks: list[str] = []
    if body is not None:
        _blocks(body, d, blocks)
    return "\n\n".join(blocks), {"paragraphs": d.paragraphs, "tables": d.tables}
