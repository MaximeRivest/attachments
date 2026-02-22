"""Tests for the HTML processor."""

from __future__ import annotations

import base64

import pytest

from attachments.deps import check_dep
from attachments.processors import processors

pytestmark = pytest.mark.skipif(
    not check_dep("html").available,
    reason="beautifulsoup4 / lxml not installed",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SIMPLE_HTML = b"""\
<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
  <h1>Hello World</h1>
  <p>First paragraph.</p>
  <p>Second paragraph.</p>
</body>
</html>
"""

HTML_WITH_SCRIPTS = b"""\
<html>
<head>
  <style>body { color: red; }</style>
  <script>alert('xss')</script>
</head>
<body>
  <p>Visible text only.</p>
  <noscript>No JS fallback</noscript>
</body>
</html>
"""

HTML_WITH_TABLE = b"""\
<html><body>
<table>
  <tr><th>Name</th><th>Age</th></tr>
  <tr><td>Alice</td><td>30</td></tr>
</table>
</body></html>
"""

# 1x1 red PNG as data URI
_TINY_PNG = base64.b64encode(
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
    b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
    b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
).decode()

HTML_WITH_DATA_IMG = (
    b'<html><body><p>See image:</p>'
    b'<img src="data:image/png;base64,' + _TINY_PNG.encode() + b'"/>'
    b'</body></html>'
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHtmlProcessor:
    def test_registered(self):
        assert ".html" in processors
        assert ".htm" in processors

    def test_overrides_text_processor(self):
        """The HTML processor should NOT be the plain text_processor."""
        from attachments.processors.text import text_processor

        assert processors[".html"] is not text_processor

    def test_basic_extraction(self):
        result = processors[".html"](SIMPLE_HTML, filename="page.html")

        assert "Hello World" in result["text"]
        assert "First paragraph" in result["text"]
        assert "Second paragraph" in result["text"]
        assert result["flags"]["kind"] == "html"
        assert result["flags"]["title"] == "Test Page"

    def test_artifact_structure(self):
        result = processors[".html"](SIMPLE_HTML)
        for key in ("text", "images", "audio", "video", "flags"):
            assert key in result

    def test_strips_scripts_and_styles(self):
        result = processors[".html"](HTML_WITH_SCRIPTS)

        assert "alert" not in result["text"]
        assert "color: red" not in result["text"]
        assert "noscript" not in result["text"].lower()
        assert "Visible text only" in result["text"]

    def test_table_text_preserved(self):
        result = processors[".html"](HTML_WITH_TABLE)

        assert "Alice" in result["text"]
        assert "30" in result["text"]

    def test_title_prepended_if_missing_from_body(self):
        html = (
            b"<html><head><title>My Title</title></head>"
            b"<body><p>Body.</p></body></html>"
        )
        result = processors[".html"](html)
        assert result["text"].startswith("My Title")

    def test_no_duplicate_title(self):
        """If the title already appears in body text, don't double it."""
        html = (
            b"<html><head><title>Hello</title></head>"
            b"<body><h1>Hello</h1><p>World.</p></body></html>"
        )
        result = processors[".html"](html)
        assert result["text"].count("Hello") == 1

    def test_images_off_by_default(self):
        result = processors[".html"](HTML_WITH_DATA_IMG)
        assert result["images"] == []

    def test_data_uri_image_extraction(self):
        result = processors[".html"](
            HTML_WITH_DATA_IMG, images=True
        )
        assert len(result["images"]) == 1
        img = result["images"][0]
        assert img["mimetype"] == "image/png"
        assert len(img["bytes"]) > 0

    def test_empty_html(self):
        result = processors[".html"](b"")
        assert isinstance(result["text"], str)
        assert "error" not in result["flags"]

    def test_non_html_garbage(self):
        result = processors[".html"](b"\x00\x01\x02binary junk")
        # bs4 is lenient — should not error, just produce empty/garbled text
        assert "error" not in result["flags"]

    def test_parser_flag(self):
        result = processors[".html"](SIMPLE_HTML)
        assert result["flags"]["parser"] in ("lxml", "html.parser")


class TestHtmlMissingDep:
    @pytest.mark.skipif(
        check_dep("html").available,
        reason="Test only relevant when bs4 is missing",
    )
    def test_missing_dep_returns_error(self):
        result = processors[".html"](b"<html></html>")
        assert "error" in result["flags"]
        assert "beautifulsoup4" in result["flags"]["error"]
