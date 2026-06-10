"""Always-runnable missing-dependency tests for the built-in processors.

The per-processor test modules skip entirely when a processor's deps are
NOT installed, which made their "deps missing" tests structurally
unrunnable (mutually exclusive skip conditions). These tests instead
simulate the absence of the optional dependencies regardless of what is
installed, and assert each processor returns the typed missing-dependency
artifact required by spec/IR-CONTRACT.md — never raising, and always
including the pip install remedy in the error message.

The simulation masks the relevant modules in ``sys.modules``: a ``None``
entry makes ``import x`` raise ImportError and makes
``importlib.util.find_spec`` report the module as unavailable, so both
guard styles (direct import and ``deps.check_dep``) are covered. The
deps cache is cleared so ``check_dep`` re-evaluates availability.
"""

from __future__ import annotations

import sys

import pytest

from attachments._processors import processors
from attachments.deps import clear_cache
from attachments.types import ERROR_MISSING_DEPENDENCY, is_missing_dependency


@pytest.fixture
def mask_modules(monkeypatch):
    """Return a callable that hides modules from the import machinery."""

    def _mask(*names: str) -> None:
        for name in names:
            monkeypatch.setitem(sys.modules, name, None)
        clear_cache()

    yield _mask
    clear_cache()


def _assert_missing_dep(result: dict) -> None:
    error = result["meta"]["error"]
    assert error["code"] == ERROR_MISSING_DEPENDENCY
    assert "pip install" in error["message"]
    assert is_missing_dependency(result)
    assert result["text"] == ""


class TestProcessorsMissingDeps:
    """Every processor's missing-dep guard returns the typed artifact."""

    def test_pdf_missing_deps_returns_typed_error(self, mask_modules):
        mask_modules("pypdf", "PyPDF2", "pdfminer")

        result = processors[".pdf"](b"%PDF-1.4 minimal pdf")

        _assert_missing_dep(result)

    def test_docx_missing_dep_returns_typed_error(self, mask_modules):
        mask_modules("docx")

        result = processors[".docx"](b"%fake")

        _assert_missing_dep(result)
        assert "pip install attachments[docx]" in result["meta"]["error"]["message"]

    def test_html_missing_dep_returns_typed_error(self, mask_modules):
        mask_modules("bs4")

        result = processors[".html"](b"<html></html>")

        _assert_missing_dep(result)
        assert "pip install attachments[html]" in result["meta"]["error"]["message"]

    def test_xlsx_missing_deps_returns_typed_error(self, mask_modules):
        mask_modules("pandas", "openpyxl")

        result = processors[".xlsx"](b"fake xlsx content")

        _assert_missing_dep(result)
        assert "pip install attachments[xlsx]" in result["meta"]["error"]["message"]

    def test_pptx_missing_dep_returns_typed_error(self, mask_modules):
        mask_modules("pptx")

        result = processors[".pptx"](b"fake pptx content")

        _assert_missing_dep(result)
        assert "pip install attachments[pptx]" in result["meta"]["error"]["message"]

    def test_image_missing_dep_returns_typed_error(self, mask_modules):
        mask_modules("PIL")

        result = processors[".png"](b"\x89PNG fake image content")

        _assert_missing_dep(result)
        assert "pip install attachments[image]" in result["meta"]["error"]["message"]

    def test_heic_missing_dep_returns_typed_error(self, mask_modules):
        mask_modules("pillow_heif")

        result = processors[".heic"](
            b"\x00\x00\x00\x18ftypheic fake", filename="photo.heic"
        )

        _assert_missing_dep(result)
        assert "pip install attachments[heic]" in result["meta"]["error"]["message"]

    def test_svg_raster_missing_dep_returns_typed_error(self, mask_modules):
        mask_modules("cairosvg")

        result = processors[".svg"](
            b"<svg xmlns='http://www.w3.org/2000/svg'/>", render_images=True
        )

        _assert_missing_dep(result)
        assert "pip install attachments[svg]" in result["meta"]["error"]["message"]

    def test_xls_missing_dep_returns_typed_error(self, mask_modules):
        mask_modules("xlrd")

        result = processors[".xls"](b"\xd0\xcf\x11\xe0 fake xls content")

        _assert_missing_dep(result)
        assert "pip install attachments[xls]" in result["meta"]["error"]["message"]
