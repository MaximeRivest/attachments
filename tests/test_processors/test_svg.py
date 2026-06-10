"""Tests for the SVG processor (stdlib text path + optional cairosvg raster)."""

from __future__ import annotations

import gzip
import sys

import pytest

from attachments._options import get_options
from attachments._processors import processors, svg
from attachments._processors.svg import svg_processor
from attachments.deps import check_dep, clear_cache
from attachments.types import ERROR_PARSE, is_missing_dependency


@pytest.fixture(autouse=True)
def _ensure_registered():
    """Re-register the svg processor for every test.

    svg.py is not yet wired into processors/__init__.py, so the conftest's
    autouse ``reset_processors()`` (which restores the built-in snapshot)
    would drop its registrations after the first test.
    """
    svg.register()


@pytest.fixture
def mask_modules(monkeypatch):
    """Hide modules from the import machinery (test_missing_deps pattern)."""

    def _mask(*names: str) -> None:
        for name in names:
            monkeypatch.setitem(sys.modules, name, None)
        clear_cache()

    yield _mask
    clear_cache()


_NS_SVG = b"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50"
     viewBox="0 0 100 50">
  <title>Chart Title</title>
  <desc>A simple chart</desc>
  <rect x="0" y="0" width="100" height="50" fill="blue"/>
  <text x="5" y="20">Hello <tspan>world</tspan></text>
</svg>
"""

_PLAIN_SVG = b"""<svg>
  <title>Plain</title>
  <text>first</text>
  <text>second <tspan>part</tspan></text>
  <textPath>curved</textPath>
</svg>
"""


class TestRegistration:
    def test_extensions_route_to_svg_processor(self):
        assert processors[".svg"] is svg_processor
        assert processors[".svgz"] is svg_processor

    def test_option_schema(self):
        for ext in (".svg", ".svgz"):
            names = [o.name for o in get_options(ext)]
            assert names == ["images"]


class TestTextExtraction:
    def test_namespaced_svg_text_in_document_order(self):
        result = svg_processor(_NS_SVG, filename="chart.svg")

        assert result["meta"].get("error") is None
        assert result["text"] == "Chart Title\nA simple chart\nHello world"
        assert result["images"] == []
        assert result["meta"]["kind"] == "vector"

    def test_namespace_free_svg(self):
        result = svg_processor(_PLAIN_SVG, filename="plain.svg")

        assert result["text"] == "Plain\nfirst\nsecond part\ncurved"
        assert result["meta"]["extra"]["has_text"] is True

    def test_empty_svg_is_not_an_error(self):
        result = svg_processor(b"<svg/>", filename="empty.svg")

        assert result["text"] == ""
        assert "error" not in result["meta"]
        assert result["meta"]["kind"] == "vector"
        assert result["meta"]["extra"]["has_text"] is False
        assert result["meta"]["extra"]["elements"] == 1


class TestExtra:
    def test_dimensions_and_viewbox_present_as_raw_strings(self):
        extra = svg_processor(_NS_SVG, filename="chart.svg")["meta"]["extra"]

        assert extra["width"] == "100"
        assert extra["height"] == "50"
        assert extra["viewBox"] == "0 0 100 50"
        assert extra["elements"] == 6

    def test_dimensions_absent_when_missing(self):
        extra = svg_processor(_PLAIN_SVG, filename="plain.svg")["meta"]["extra"]

        for key in ("width", "height", "viewBox", "compressed", "renderer"):
            assert key not in extra


class TestSvgz:
    def test_svgz_round_trip(self):
        result = svg_processor(gzip.compress(_NS_SVG), filename="chart.svgz")

        assert result["text"] == "Chart Title\nA simple chart\nHello world"
        assert result["meta"]["extra"]["compressed"] is True

    def test_magic_sniffed_gzip_under_svg_extension(self):
        result = svg_processor(gzip.compress(_PLAIN_SVG), filename="plain.svg")

        assert result["text"].startswith("Plain")
        assert result["meta"]["extra"]["compressed"] is True

    def test_bad_gzip_is_parse_error(self):
        result = svg_processor(b"\x1f\x8bnot really gzip", filename="bad.svgz")

        assert result["meta"]["error"]["code"] == ERROR_PARSE


class TestErrors:
    def test_malformed_xml_is_parse_error(self):
        result = svg_processor(b"<svg><unclosed", filename="bad.svg")

        assert result["meta"]["error"]["code"] == ERROR_PARSE
        assert "parse" in result["meta"]["error"]["message"].lower()


class TestRasterOptIn:
    def test_default_never_rasters_even_with_cairosvg(self):
        result = svg_processor(_NS_SVG, filename="chart.svg")

        assert result["images"] == []
        assert "renderer" not in result["meta"]["extra"]

    def test_explicit_request_without_cairosvg_is_typed_missing_dep(self, mask_modules):
        mask_modules("cairosvg")

        result = svg_processor(_NS_SVG, filename="chart.svg", render_images=True)

        assert is_missing_dependency(result)
        assert "pip install attachments[svg]" in result["meta"]["error"]["message"]

    def test_auto_without_cairosvg_keeps_text_with_render_skipped(self, mask_modules):
        mask_modules("cairosvg")

        result = svg_processor(_NS_SVG, filename="chart.svg", render_images="auto")

        assert not is_missing_dependency(result)
        assert result["text"] == "Chart Title\nA simple chart\nHello world"
        assert result["images"] == []
        assert result["meta"]["extra"]["render_skipped"] == "cairosvg not installed"


@pytest.mark.skipif(not check_dep("svg").available, reason="cairosvg not installed")
class TestRaster:
    @pytest.mark.parametrize("value", [True, "always", "auto"])
    def test_renders_one_png_image_item(self, value):
        result = svg_processor(_NS_SVG, filename="chart.svg", render_images=value)

        assert len(result["images"]) == 1
        item = result["images"][0]
        assert item["name"] == "chart.png"
        assert item["mimetype"] == "image/png"
        assert item["bytes"][:4] == b"\x89PNG"
        assert result["meta"]["extra"]["renderer"] == "cairosvg"
        assert result["text"] == "Chart Title\nA simple chart\nHello world"

    def test_raster_failure_keeps_text_and_warns(self, monkeypatch):
        import cairosvg

        def _boom(**_):
            raise ValueError("css explosion")

        monkeypatch.setattr(cairosvg, "svg2png", _boom)

        result = svg_processor(_NS_SVG, filename="chart.svg", render_images=True)

        assert result["text"] == "Chart Title\nA simple chart\nHello world"
        assert result["images"] == []
        assert any(
            w.startswith("rasterization failed:") for w in result["meta"]["warnings"]
        )
        assert "renderer" not in result["meta"]["extra"]
