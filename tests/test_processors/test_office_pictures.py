"""Pictures of Office pages, slides and sheets (``images: true``).

Drawing needs LibreOffice and PyMuPDF (skipped otherwise); the behaviour
without LibreOffice (missing-dependency, ``auto``) is tested everywhere.
"""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

import pytest

from attachments import att
from attachments.deps import check_dep, find_libreoffice
from attachments.types import is_missing_dependency

SOFFICE = find_libreoffice()
can_draw = pytest.mark.skipif(
    SOFFICE is None or not check_dep("pdf-images").available,
    reason="needs LibreOffice and PyMuPDF",
)


def _size(data: bytes) -> tuple[int, int]:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as img:
        return img.size


@pytest.fixture
def deck(tmp_path: Path) -> Path:
    pptx = pytest.importorskip("pptx")
    prs = pptx.Presentation()
    for title in ("One", "Two (hidden)", "Three"):
        prs.slides.add_slide(prs.slide_layouts[1]).shapes.title.text = title
    prs.slides[1]._element.set("show", "0")  # a hidden slide
    path = tmp_path / "deck.pptx"
    prs.save(path)
    return path


@pytest.fixture
def book(tmp_path: Path) -> Path:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    wb.active.title = "Sales"
    for r in range(1, 30):
        wb.active.append([f"row {r}", r, r * 2])
    hidden = wb.create_sheet("Hidden")
    hidden["A1"] = "kept"
    hidden.sheet_state = "hidden"
    wb.create_sheet("Empty")
    wb.create_sheet("Notes")["A1"] = "a note"
    path = tmp_path / "book.xlsx"
    wb.save(path)
    return path


@pytest.fixture
def document(tmp_path: Path) -> Path:
    docx = pytest.importorskip("docx")
    doc = docx.Document()
    doc.add_heading("Report", level=1)
    doc.add_paragraph("First page.")
    doc.add_page_break()
    doc.add_paragraph("Second page.")
    path = tmp_path / "report.docx"
    doc.save(path)
    return path


def _convert(path: Path, target: str) -> Path:
    subprocess.run(
        [
            SOFFICE,
            f"-env:UserInstallation={(path.parent / 'lo-profile').as_uri()}",
            "--headless",
            "--convert-to",
            target,
            "--outdir",
            str(path.parent),
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    return path.with_suffix(f".{target}")


@can_draw
class TestDrawing:
    def test_word_pages(self, document):
        [a] = att(f"{document}[images: true]")
        assert [im["name"] for im in a["images"]] == [
            "report.docx-page-1.png",
            "report.docx-page-2.png",
        ]
        assert [im["page"] for im in a["images"]] == [1, 2]
        assert a["meta"]["extra"]["picture_renderer"] == "libreoffice+pymupdf"
        assert "Second page." in a["text"]

    def test_slides_line_up_with_their_text_hidden_ones_included(self, deck):
        [a] = att(f"{deck}[images: true]")
        assert [s["page"] for s in a["meta"]["segments"]] == [1, 2, 3]
        assert [im["page"] for im in a["images"]] == [1, 2, 3]
        assert a["images"][1]["name"] == "deck.pptx-slide-2.png"

    def test_selected_slides_only(self, deck):
        [a] = att(f"{deck}[images: true, pages: 2-]")
        assert [im["page"] for im in a["images"]] == [2, 3]

    def test_one_picture_per_sheet_empty_ones_skipped(self, book):
        [a] = att(f"{book}[images: true]")
        assert [(s["label"], s["page"]) for s in a["meta"]["segments"]] == [
            ("Sales", 1),
            ("Hidden", 2),
            ("Empty", 3),
            ("Notes", 4),
        ]
        assert [im["page"] for im in a["images"]] == [1, 2, 4]
        assert a["meta"]["extra"]["blank_sheets"] == 1

    def test_selected_sheet_only(self, book):
        [a] = att(f"{book}[images: true, sheet: Notes]")
        assert [im["page"] for im in a["images"]] == [4]

    def test_size_and_format(self, deck):
        [a] = att(f"{deck}[images: true, max_dim: 400, image_format: jpeg, pages: 1]")
        [image] = a["images"]
        assert image["mimetype"] == "image/jpeg" and image["name"].endswith(".jpg")
        assert max(_size(image["bytes"])) == 400

    @pytest.mark.parametrize(("source", "target"), [("deck", "ppt"), ("book", "ods")])
    def test_old_formats_are_drawn_from_the_original(
        self, request, monkeypatch, source, target
    ):
        original = _convert(request.getfixturevalue(source), target)
        from attachments._processors import legacy_office

        drawn_from: list[str] = []
        real = legacy_office.convert

        def spy(data, source_ext, target_ext, *args, **kwargs):
            if target_ext == ".pdf":
                drawn_from.append(source_ext)
            return real(data, source_ext, target_ext, *args, **kwargs)

        monkeypatch.setattr(legacy_office, "convert", spy)
        [a] = att(f"{original}[images: true]")
        assert drawn_from == [f".{target}"]  # not the converted copy
        assert a["images"] and a["meta"]["extra"]["converted_from"] == f".{target}"


class TestWithoutLibreOffice:
    @pytest.fixture(autouse=True)
    def no_libreoffice(self, monkeypatch):
        monkeypatch.setattr(
            "attachments._processors._office_pages.find_libreoffice", lambda: None
        )

    def test_true_is_a_missing_dependency(self, deck):
        [a] = att(f"{deck}[images: true]")
        assert is_missing_dependency(a)
        assert "LibreOffice" in a["meta"]["error"]["message"]

    def test_auto_keeps_the_text_with_a_note(self, deck):
        [a] = att(f"{deck}[images: auto]")
        assert "# One" in a["text"] and a["images"] == []
        assert "LibreOffice is not installed" in a["meta"]["note"]

    def test_embedded_pictures_need_no_libreoffice(self, document):
        [a] = att(f"{document}[embedded_images: true]")
        assert "error" not in a["meta"]


def test_invalid_picture_options_are_typed_errors(deck):
    for bad in ({"dpi": 5}, {"image_format": "gif"}, {"quality": 0}):
        [a] = att(str(deck), images=True, **bad)
        assert a["meta"]["error"]["code"] == "invalid-option"


def test_sheets_have_no_embedded_images_option():
    names = {o["name"] for o in att.options(".xlsx")}
    assert "images" in names and "embedded_images" not in names
