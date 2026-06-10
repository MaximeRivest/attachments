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


class TestRegistration:
    @pytest.mark.parametrize(
        "ext", [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif"]
    )
    def test_extension_registered_with_max_dim_option(self, ext):
        assert processors[ext] is image_processor
        names = [o.name for o in get_options(ext)]
        assert names == ["max_dim"]
