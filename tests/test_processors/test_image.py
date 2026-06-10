"""Tests for the image processor (Pillow-backed)."""

from __future__ import annotations

import io
import sys

import pytest

from attachments._options import get_options
from attachments._processors import image, processors
from attachments._processors.image import image_processor
from attachments.deps import check_dep, clear_cache
from attachments.types import (
    ERROR_MISSING_DEPENDENCY,
    ERROR_PARSE,
    is_missing_dependency,
)

pytestmark = pytest.mark.skipif(
    not check_dep("image").available,
    reason="Pillow not installed",
)


@pytest.fixture(autouse=True)
def _ensure_registered():
    """Re-register the image processor for every test.

    image.py is not yet wired into processors/__init__.py, so the conftest's
    autouse ``reset_processors()`` (which restores the built-in snapshot)
    would drop its registrations after the first test.
    """
    image.register()


def _make_image_bytes(fmt: str, size=(8, 8), mode="RGB", color=(255, 0, 0)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new(mode, size, color).save(buf, format=fmt)
    return buf.getvalue()


def _decode(item: dict):
    from PIL import Image

    img = Image.open(io.BytesIO(item["bytes"]))
    img.load()
    return img


@pytest.fixture
def mask_modules(monkeypatch):
    """Hide modules from the import machinery (test_missing_deps pattern)."""

    def _mask(*names: str) -> None:
        for name in names:
            monkeypatch.setitem(sys.modules, name, None)
        clear_cache()

    yield _mask
    clear_cache()


class TestPassthrough:
    @pytest.mark.parametrize(
        ("fmt", "mimetype"),
        [
            ("PNG", "image/png"),
            ("JPEG", "image/jpeg"),
            ("GIF", "image/gif"),
            ("WEBP", "image/webp"),
        ],
    )
    def test_web_formats_pass_through_untouched(self, fmt, mimetype):
        data = _make_image_bytes(fmt)

        result = image_processor(data, filename=f"pic.{fmt.lower()}")

        assert len(result["images"]) == 1
        item = result["images"][0]
        assert item["bytes"] == data  # original bytes, no re-encode
        assert item["mimetype"] == mimetype
        assert item["name"] == f"pic.{fmt.lower()}"
        assert result["text"] == ""
        assert result["meta"]["kind"] == "image"
        assert "error" not in result["meta"]

    def test_extra_fields_and_no_resized_flag(self):
        data = _make_image_bytes("PNG", size=(8, 6))

        extra = image_processor(data)["meta"]["extra"]

        assert extra["width"] == 8
        assert extra["height"] == 6
        assert extra["original_format"] == "PNG"
        assert extra["mode"] == "RGB"
        assert "resized" not in extra

    def test_max_dim_not_exceeded_keeps_passthrough(self):
        data = _make_image_bytes("PNG", size=(8, 8))

        result = image_processor(data, max_dim=16)

        assert result["images"][0]["bytes"] == data
        assert "resized" not in result["meta"]["extra"]


class TestReencode:
    def test_bmp_reencodes_to_png(self):
        data = _make_image_bytes("BMP")

        result = image_processor(data, filename="photo.bmp")

        item = result["images"][0]
        assert item["bytes"] != data
        assert item["mimetype"] == "image/png"
        assert item["name"] == "photo.png"
        assert _decode(item).format == "PNG"
        extra = result["meta"]["extra"]
        assert extra["original_format"] == "BMP"
        assert "resized" not in extra

    def test_max_dim_resizes_preserving_aspect(self):
        data = _make_image_bytes("PNG", size=(64, 32))

        result = image_processor(data, filename="wide.png", max_dim=16)

        item = result["images"][0]
        assert item["bytes"] != data  # re-encoded
        assert item["mimetype"] == "image/png"
        assert item["name"] == "wide.png"
        assert _decode(item).size == (16, 8)
        extra = result["meta"]["extra"]
        assert extra["width"] == 16
        assert extra["height"] == 8
        assert extra["resized"] is True

    def test_jpeg_resize_stays_jpeg(self):
        data = _make_image_bytes("JPEG", size=(64, 32))

        result = image_processor(data, filename="photo.jpeg", max_dim=16)

        item = result["images"][0]
        assert item["mimetype"] == "image/jpeg"
        assert item["name"] == "photo.jpg"
        decoded = _decode(item)
        assert decoded.format == "JPEG"
        assert decoded.size == (16, 8)
        assert result["meta"]["extra"]["resized"] is True


class TestErrors:
    def test_corrupt_bytes_return_parse_error(self):
        result = image_processor(b"not an image at all", filename="bad.png")

        assert result["meta"]["error"]["code"] == ERROR_PARSE
        assert result["meta"]["source"] == "bad.png"
        assert result["text"] == ""
        assert result["images"] == []

    def test_truncated_png_returns_parse_error(self):
        data = _make_image_bytes("PNG", size=(32, 32))

        result = image_processor(data[: len(data) // 2])

        assert result["meta"]["error"]["code"] == ERROR_PARSE

    def test_missing_pillow_returns_typed_artifact(self, mask_modules):
        mask_modules("PIL")

        result = image_processor(b"\x89PNG fake", filename="pic.png")

        assert is_missing_dependency(result)
        error = result["meta"]["error"]
        assert error["code"] == ERROR_MISSING_DEPENDENCY
        assert "pip install attachments[image]" in error["message"]
        assert result["text"] == ""

    def test_missing_pillow_default_source_name(self, mask_modules):
        mask_modules("PIL")

        result = image_processor(b"")

        assert result["meta"]["source"] == "image"
        assert is_missing_dependency(result)


class TestRotate:
    def _two_tone_png(self, size=(64, 32)) -> bytes:
        """Red image with a distinct blue pixel in the top-left corner."""
        from PIL import Image

        img = Image.new("RGB", size, (255, 0, 0))
        img.putpixel((0, 0), (0, 0, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_rotate_90_is_counterclockwise(self):
        data = self._two_tone_png((64, 32))

        result = image_processor(data, filename="wide.png", rotate=90)

        item = result["images"][0]
        decoded = _decode(item)
        assert decoded.size == (32, 64)
        # CCW: the blue top-left corner moves to the bottom-left corner.
        assert decoded.getpixel((0, 63)) == (0, 0, 255)
        assert decoded.getpixel((0, 0)) == (255, 0, 0)
        extra = result["meta"]["extra"]
        assert extra["rotated"] == 90
        assert extra["width"] == 32
        assert extra["height"] == 64

    def test_rotate_forces_reencode_for_png(self):
        # Two-tone so the rotated pixels (and thus the bytes) actually differ.
        data = self._two_tone_png((8, 8))

        result = image_processor(data, filename="pic.png", rotate=90)

        assert result["images"][0]["bytes"] != data

    def test_rotate_applied_before_max_dim(self):
        data = _make_image_bytes("PNG", size=(64, 32))

        result = image_processor(data, rotate=90, max_dim=32)

        # Rotated to 32x64, then thumbnailed to fit 32 → (16, 32).
        assert _decode(result["images"][0]).size == (16, 32)
        extra = result["meta"]["extra"]
        assert extra["rotated"] == 90
        assert extra["resized"] is True

    @pytest.mark.parametrize("degrees", [0, 360])
    def test_rotate_noop_keeps_passthrough(self, degrees):
        data = _make_image_bytes("PNG", size=(8, 8))

        result = image_processor(data, filename="pic.png", rotate=degrees)

        assert result["images"][0]["bytes"] == data
        assert "rotated" not in result["meta"]["extra"]


class TestHeic:
    def _heic_bytes(self, size=(8, 8)) -> bytes:
        from pillow_heif import register_heif_opener

        register_heif_opener()
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", size, (0, 128, 255)).save(buf, format="HEIF")
        return buf.getvalue()

    def test_heic_missing_pillow_heif_returns_typed_artifact(self, mask_modules):
        mask_modules("pillow_heif")

        result = image_processor(b"\x00\x00\x00\x18ftypheic fake", filename="pic.heic")

        assert is_missing_dependency(result)
        error = result["meta"]["error"]
        assert error["code"] == ERROR_MISSING_DEPENDENCY
        assert "attachments[heic]" in error["message"]

    @pytest.mark.parametrize("filename", ["pic.heic", "pic.HEIF", None])
    def test_heic_detected_by_extension_or_magic(self, filename, mask_modules):
        mask_modules("pillow_heif")

        result = image_processor(b"\x00\x00\x00\x18ftypmif1 fake", filename=filename)

        assert is_missing_dependency(result)
        assert "attachments[heic]" in result["meta"]["error"]["message"]

    def test_png_unaffected_by_missing_pillow_heif(self, mask_modules):
        mask_modules("pillow_heif")
        data = _make_image_bytes("PNG")

        result = image_processor(data, filename="pic.png")

        assert "error" not in result["meta"]
        assert result["images"][0]["bytes"] == data

    @pytest.mark.skipif(
        not check_dep("heic").available, reason="pillow-heif not installed"
    )
    def test_heic_roundtrips_to_png(self):
        data = self._heic_bytes()

        result = image_processor(data, filename="photo.heic")

        item = result["images"][0]
        assert item["mimetype"] == "image/png"
        assert item["name"] == "photo.png"
        assert _decode(item).format == "PNG"
        assert result["meta"]["extra"]["original_format"] == "HEIF"


class TestRegistration:
    @pytest.mark.parametrize(
        "ext",
        [
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".webp",
            ".bmp",
            ".tiff",
            ".tif",
            ".heic",
            ".heif",
        ],
    )
    def test_extension_registered_with_options(self, ext):
        assert processors[ext] is image_processor
        names = [o.name for o in get_options(ext)]
        assert names == ["max_dim", "rotate", "ocr"]


def _text_image_bytes(text: str = "HELLO WORLD 42") -> bytes:
    """Render large, clear black-on-white text into a PNG (OCR fixture)."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (600, 200), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=60)
    except TypeError:  # older Pillow: load_default() takes no size kwarg
        font = ImageFont.load_default()
    draw.text((20, 60), text, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestImageOcr:
    """ocr option: False (default) | True | "auto"."""

    def test_ocr_default_off(self):
        result = image_processor(_text_image_bytes(), filename="sign.png")

        assert "error" not in result["meta"]
        assert result["text"] == ""
        assert "ocr" not in result["meta"]["extra"]

    def test_ocr_false_never_runs(self):
        result = image_processor(_text_image_bytes(), filename="sign.png", ocr=False)

        assert result["text"] == ""
        assert "ocr" not in result["meta"]["extra"]

    @pytest.mark.skipif(
        not check_dep("ocr").available, reason="rapidocr_onnxruntime not installed"
    )
    def test_ocr_true_recognizes_text(self):
        # Real CPU inference; the first call also loads the model (slow,
        # but the engine is cached at module level for the whole session).
        result = image_processor(_text_image_bytes(), filename="sign.png", ocr=True)

        assert "error" not in result["meta"]
        assert "HELLO WORLD 42" in result["text"]
        extra = result["meta"]["extra"]
        assert extra["ocr"] is True
        assert extra["ocr_backend"] == "rapidocr"
        assert result["images"]  # the image item is still emitted

    @pytest.mark.skipif(
        not check_dep("ocr").available, reason="rapidocr_onnxruntime not installed"
    )
    def test_ocr_auto_behaves_like_true_when_installed(self):
        result = image_processor(_text_image_bytes(), filename="sign.png", ocr="auto")

        assert "HELLO WORLD 42" in result["text"]
        assert result["meta"]["extra"]["ocr"] is True

    def test_ocr_true_missing_dep_returns_typed_error(self, mask_modules):
        mask_modules("rapidocr_onnxruntime")

        result = image_processor(_text_image_bytes(), filename="sign.png", ocr=True)

        assert is_missing_dependency(result)
        error = result["meta"]["error"]
        assert error["code"] == ERROR_MISSING_DEPENDENCY
        assert "pip install attachments[ocr]" in error["message"]

    def test_ocr_auto_missing_dep_is_noop_with_hint(self, mask_modules):
        mask_modules("rapidocr_onnxruntime")

        result = image_processor(_text_image_bytes(), filename="sign.png", ocr="auto")

        assert "error" not in result["meta"]
        assert result["text"] == ""
        assert "pip install attachments[ocr]" in result["meta"]["extra"]["ocr_hint"]
