# ruff: noqa: E501  (Word XML fixtures)
"""The Word reader (_docx_text): what Word keeps out of plain sight.

Each case was missed by the earlier python-docx-based reader on the test
files of markitdown and docling (see the comparison in attachments-bench).
"""

from __future__ import annotations

import io
import zipfile

from attachments import att
from attachments._processors._docx_text import docx_markdown

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
STRICT = "http://purl.oclc.org/ooxml/wordprocessingml/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"


def p(text: str, props: str = "") -> str:
    return f"<w:p>{props}<w:r><w:t xml:space='preserve'>{text}</w:t></w:r></w:p>"


def tc(content: str, props: str = "") -> str:
    return f"<w:tc>{props}{content}</w:tc>"


def docx(body: str, *, ns: str = W, styles: str = "", numbering: str = "") -> bytes:
    head = f'xmlns:w="{ns}" xmlns:mc="{MC}"'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr(
            "word/document.xml",
            f"<w:document {head}><w:body>{body}</w:body></w:document>",
        )
        if styles:
            z.writestr(
                "word/styles.xml", f'<w:styles xmlns:w="{ns}">{styles}</w:styles>'
            )
        if numbering:
            z.writestr(
                "word/numbering.xml",
                f'<w:numbering xmlns:w="{ns}">{numbering}</w:numbering>',
            )
    return buffer.getvalue()


def text(body: str, **kw) -> str:
    return docx_markdown(docx(body, **kw))[0]


def test_table_inside_a_content_control():
    body = (
        "<w:sdt><w:sdtContent><w:tbl>"
        f"<w:tr>{tc(p('Feature'))}{tc(p('Action'))}</w:tr>"
        f"<w:tr>{tc(p('Order'))}{tc(p('Reorganize'))}</w:tr>"
        "</w:tbl></w:sdtContent></w:sdt>"
    )
    assert text(body) == "| Feature | Action |\n| --- | --- |\n| Order | Reorganize |"


def test_cells_inside_content_controls_in_a_row():
    row = f"<w:tr><w:sdt><w:sdtContent>{tc(p('a'))}</w:sdtContent></w:sdt>{tc(p('b'))}</w:tr>"
    assert text(f"<w:tbl>{row}{row}</w:tbl>").startswith("| a | b |")


def test_text_box_read_once_after_its_paragraph():
    box = f"<w:txbxContent>{p('Inside the box')}</w:txbxContent>"
    run = (
        "<w:r><mc:AlternateContent>"
        f"<mc:Choice Requires='wps'><w:drawing>{box}</w:drawing></mc:Choice>"
        f"<mc:Fallback><w:pict>{box}</w:pict></mc:Fallback>"
        "</mc:AlternateContent></w:r>"
    )
    body = f"<w:p><w:r><w:t>Anchor</w:t></w:r>{run}</w:p>"
    assert text(body) == "Anchor\n\nInside the box"


def test_merged_cells():
    across = '<w:tcPr><w:gridSpan w:val="2"/></w:tcPr>'
    down = '<w:tcPr><w:vMerge w:val="restart"/></w:tcPr>'
    more = "<w:tcPr><w:vMerge/></w:tcPr>"
    body = (
        "<w:tbl>"
        f"<w:tr>{tc(p('H1'))}{tc(p('H2'))}{tc(p('H3'))}</w:tr>"
        f"<w:tr>{tc(p('Across'), across)}{tc(p('Down'), down)}</w:tr>"
        f"<w:tr>{tc(p('x'))}{tc(p('y'))}{tc(p(''), more)}</w:tr>"
        "</w:tbl>"
    )
    assert text(body).splitlines()[2:] == ["| Across |  | Down |", "| x | y | Down |"]


def test_cell_with_several_paragraphs_stays_on_one_line():
    body = f"<w:tbl><w:tr>{tc(p('a'))}{tc(p('b'))}</w:tr><w:tr>{tc(p('one') + p('two'))}{tc(p('x|y'))}</w:tr></w:tbl>"
    assert text(body).splitlines()[-1] == "| one<br>two | x\\|y |"


def test_one_cell_frame_is_read_as_its_content():
    inner = f"<w:tbl><w:tr>{tc(p('a'))}{tc(p('b'))}</w:tr><w:tr>{tc(p('1'))}{tc(p('2'))}</w:tr></w:tbl>"
    body = f"<w:tbl><w:tr>{tc(p('Title') + inner)}</w:tr></w:tbl>"
    assert text(body) == "Title\n\n| a | b |\n| --- | --- |\n| 1 | 2 |"


def test_headings_and_lists():
    styles = (
        '<w:style w:styleId="H1"><w:name w:val="heading 1"/></w:style>'
        '<w:style w:styleId="Mine"><w:name w:val="My heading"/><w:basedOn w:val="H1"/></w:style>'
    )
    numbering = (
        '<w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/></w:lvl>'
        '<w:lvl w:ilvl="1"><w:numFmt w:val="bullet"/></w:lvl></w:abstractNum>'
        '<w:num w:numId="5"><w:abstractNumId w:val="0"/></w:num>'
    )
    num = '<w:pPr><w:numPr><w:ilvl w:val="{}"/><w:numId w:val="5"/></w:numPr></w:pPr>'
    body = (
        p("Report", '<w:pPr><w:pStyle w:val="H1"/></w:pPr>')
        + p("Based on a heading", '<w:pPr><w:pStyle w:val="Mine"/></w:pPr>')
        + p("first", num.format(0))
        + p("detail", num.format(1))
    )
    assert text(body, styles=styles, numbering=numbering).splitlines()[::2] == [
        "# Report",
        "# Based on a heading",
        "1. first",
        "  - detail",
    ]


def test_tracked_changes_show_the_result():
    body = (
        "<w:p><w:r><w:t xml:space='preserve'>Keep </w:t></w:r>"
        "<w:del><w:r><w:delText>removed </w:delText></w:r></w:del>"
        "<w:ins><w:r><w:t>added</w:t></w:r></w:ins></w:p>"
    )
    assert text(body) == "Keep added"


def test_strict_format():
    assert text(p("Strict text"), ns=STRICT) == "Strict text"


def test_through_att(tmp_path):
    path = tmp_path / "form.docx"
    path.write_bytes(
        docx(f"<w:sdt><w:sdtContent>{p('Filled in')}</w:sdtContent></w:sdt>")
    )
    result = att(str(path))[0]
    assert result["text"] == "Filled in"
    assert result["meta"]["extra"]["paragraphs"] == 1


def test_not_a_word_file_is_a_parse_error(tmp_path):
    path = tmp_path / "broken.docx"
    path.write_bytes(b"not a zip")
    assert att(str(path))[0]["meta"]["error"]["code"] == "parse-error"
