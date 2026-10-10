"""Tests for picture labels (the ``watermark`` option, ``_watermark.py``).

=============================================================================
TEST GUIDELINES
=============================================================================

GOOD tests:
    - Labels through att(): the strip is there, the picture keeps its size,
      JPEG stays JPEG, page/name/custom text, meta.extra.watermark
    - Every "could not" is a warning, never an exception (no pictures, no
      page, a text file)
    - Core applies the label after the service too, and never sends it
    - sources=False warns when a label carries the file name
    - The label is legible (OCR reads it back) when rapidocr is installed

BAD tests:
    - Pixel-exact comparisons of the drawn text (fonts differ by Pillow)
=============================================================================
"""

from __future__ import annotations

import io
import warnings
from pathlib import Path

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

from attachments import att, make_artifact, missing_dep_artifact  # noqa: E402
from attachments._options import register_options  # noqa: E402
from attachments._processors import register_processor  # noqa: E402
from attachments._watermark import WATERMARK, label_picture  # noqa: E402
from attachments.core import _process_single  # noqa: E402


def _image(size=(1200, 900), color="steelblue", fmt="PNG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    return buf.getvalue()


def _open(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


def _strip_is_white(data: bytes) -> bool:
    img = _open(data).convert("RGB")
    return img.getpixel((img.width // 2, 2)) == (255, 255, 255)


@pytest.fixture
def pdf(tmp_path: Path) -> Path:
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    for number in (1, 2, 3):
        page = doc.new_page()
        page.insert_text((72, 100), f"Text of page {number}.", fontsize=18)
    path = tmp_path / "report.pdf"
    doc.save(path)
    return path


class TestLabels:
    def test_pdf_pages_get_their_page(self, pdf: Path):
        plain = att(f"{pdf}[images: true, max_dim: 800]")[0]
        labelled = att(f"{pdf}[images: true, max_dim: 800, watermark: page]")[0]
        assert labelled["meta"]["extra"]["watermark"] == "{page}"
        for before, after in zip(plain["images"], labelled["images"], strict=True):
            assert _open(after["bytes"]).size == _open(before["bytes"]).size
            assert after["page"] == before["page"]
            assert after["name"] == before["name"]
            assert _strip_is_white(after["bytes"])
        assert "warnings" not in labelled["meta"]

    def test_off_by_default(self, tmp_path: Path):
        photo = tmp_path / "cat.png"
        photo.write_bytes(_image())
        img = att(str(photo))[0]
        assert not _strip_is_white(img["images"][0]["bytes"])
        assert "watermark" not in img["meta"].get("extra", {})
        off = att(str(photo), watermark="off")[0]
        assert off["images"][0]["bytes"] == img["images"][0]["bytes"]

    def test_photo_keeps_jpeg_and_size(self, tmp_path: Path):
        photo = tmp_path / "cat.jpg"
        photo.write_bytes(_image(fmt="JPEG"))
        out = att(str(photo), watermark="name")[0]
        image = out["images"][0]
        assert image["mimetype"] == "image/jpeg"
        assert _open(image["bytes"]).format == "JPEG"
        assert _open(image["bytes"]).size == (1200, 900)
        assert out["meta"]["extra"]["watermark"] == "{name} · {page}"

    def test_gif_becomes_png(self, tmp_path: Path):
        anim = tmp_path / "anim.gif"
        anim.write_bytes(_image(size=(400, 300), fmt="GIF"))
        image = att(f"{anim}[watermark: Exhibit A]")[0]["images"][0]
        assert (image["mimetype"], image["name"]) == ("image/png", "anim.png")
        assert _open(image["bytes"]).format == "PNG"

    def test_tiny_picture_grows_instead(self):
        out, _ = label_picture(_image(size=(60, 40)), "image/png", "page 1")
        width, height = _open(out).size
        assert width == 60 and height > 40

    def test_transparent_png_stays_transparent(self):
        buf = io.BytesIO()
        Image.new("RGBA", (400, 400), (0, 0, 0, 0)).save(buf, "PNG")
        out, _ = label_picture(buf.getvalue(), "image/png", "logo")
        img = _open(out)
        assert img.mode == "RGBA"
        assert img.getpixel((200, 300))[3] == 0  # content still transparent
        assert img.getpixel((200, 2)) == (255, 255, 255, 255)  # strip opaque

    def test_long_label_is_shortened_not_cut_off(self):
        name = "a-very-long-file-name-" * 10 + ".pdf"
        out, _ = label_picture(_image(size=(300, 300)), "image/png", name)
        assert _open(out).size == (300, 300)


class TestWarnings:
    def test_no_pictures_names_the_option_that_makes_them(self, pdf: Path):
        out = att(f"{pdf}[watermark: page]")[0]
        assert out["meta"]["warnings"] == [
            "watermark: report.pdf has no pictures to label "
            "— ask for them with images: true"
        ]

    def test_page_label_on_a_photo(self, tmp_path: Path):
        photo = tmp_path / "cat.png"
        photo.write_bytes(_image())
        out = att(f"{photo}[watermark: page]")[0]
        assert "have no page to show" in out["meta"]["warnings"][0]
        assert "watermark" not in out["meta"].get("extra", {})

    def test_text_file_does_not_take_it(self, tmp_path: Path):
        notes = tmp_path / "notes.txt"
        notes.write_text("hello")
        out = att(f"{notes}[watermark: page]")[0]
        assert "Unknown option 'watermark'" in out["meta"]["warnings"][0]

    def test_is_an_option_warning_at_the_callers_line(self, pdf: Path):
        from attachments import OptionWarning

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            att(f"{pdf}[watermark: page]")
        found = [w for w in caught if issubclass(w.category, OptionWarning)]
        assert found and Path(found[0].filename).name == "test_watermark.py"

    def test_sources_false_warns_when_the_name_is_drawn(self, tmp_path: Path):
        photo = tmp_path / "tabby_cat.png"
        photo.write_bytes(_image())
        named = att(f"{photo}[watermark: name]")
        with pytest.warns(UserWarning, match="carry their file name"):
            named.parts(sources=False)
        paged = att(f"{photo}[watermark: Exhibit {{page}}]")
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            paged.parts(sources=False)


class TestCore:
    def test_applied_after_the_service_and_never_sent(self, monkeypatch):
        """A file read by the service is labelled here, the same way."""

        @register_processor(".pic")
        def _missing(data: bytes, **_):
            return missing_dep_artifact("a.pic", "image")

        register_options(".pic", (WATERMARK,))
        sent = {}

        def _service(filename, data, key, *, options=None):
            sent.update(options or {})
            image = {"name": "a.png", "mimetype": "image/png", "bytes": _image()}
            return make_artifact(images=[image], meta={"via": "service"})

        monkeypatch.setattr("attachments.core._process_via_service", _service)
        out = _process_single("a.pic", b"x", options={"watermark": "name"}, api_key="k")
        assert "watermark" not in sent
        assert out["meta"]["via"] == "service"
        assert _strip_is_white(out["images"][0]["bytes"])

    def test_processor_never_receives_it(self):
        seen = {}

        @register_processor(".pic")
        def _proc(data: bytes, **options):
            seen.update(options)
            return make_artifact()

        register_options(".pic", (WATERMARK,))
        _process_single("a.pic", b"x", options={"watermark": "page"})
        assert "watermark" not in seen

    def test_failed_file_is_left_alone(self):
        @register_processor(".pic")
        def _missing(data: bytes, **_):
            return missing_dep_artifact("a.pic", "image")

        register_options(".pic", (WATERMARK,))
        out = _process_single("a.pic", b"x", options={"watermark": "page"})
        assert out["meta"]["error"]["code"] == "missing-dependency"
        assert "warnings" not in out["meta"]


def test_label_is_legible(tmp_path: Path):
    """What a model would read: OCR finds the label in the strip."""
    pytest.importorskip("rapidocr")
    from attachments.deps import check_dep

    if not check_dep("ocr").available:
        pytest.skip("rapidocr not usable")
    from attachments._processors._ocr import recognize

    out, _ = label_picture(
        _image(size=(1414, 2000), color="white"), "image/png", "report.pdf · page 7"
    )
    strip = _open(out).convert("RGB").crop((0, 0, 1414, 120))
    text = recognize(strip).text
    assert "page 7" in text and "report" in text
