"""Tests for the HTML processor."""

from __future__ import annotations

import base64

import pytest

from attachments._processors import processors
from attachments.deps import check_dep

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
    b"<html><body><p>See image:</p>"
    b'<img src="data:image/png;base64,' + _TINY_PNG.encode() + b'"/>'
    b"</body></html>"
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
        from attachments._processors.text import text_processor

        assert processors[".html"] is not text_processor

    def test_basic_extraction(self):
        result = processors[".html"](SIMPLE_HTML, filename="page.html")

        assert "Hello World" in result["text"]
        assert "First paragraph" in result["text"]
        assert "Second paragraph" in result["text"]
        assert result["meta"]["kind"] == "html"
        assert result["meta"]["extra"]["title"] == "Test Page"

    def test_artifact_structure(self):
        result = processors[".html"](SIMPLE_HTML)
        for key in ("text", "images", "audio", "video", "meta"):
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
        assert result["text"].startswith("# My Title\n\nBody.")

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
        result = processors[".html"](HTML_WITH_DATA_IMG, images=True)
        assert len(result["images"]) == 1
        img = result["images"][0]
        assert img["mimetype"] == "image/png"
        assert len(img["bytes"]) > 0

    def test_empty_html(self):
        result = processors[".html"](b"")
        assert isinstance(result["text"], str)
        assert "error" not in result["meta"]

    def test_non_html_garbage(self):
        result = processors[".html"](b"\x00\x01\x02binary junk")
        # bs4 is lenient — should not error, just produce empty/garbled text
        assert "error" not in result["meta"]

    def test_parser_in_extra(self):
        result = processors[".html"](SIMPLE_HTML)
        assert result["meta"]["extra"]["parser"] in ("lxml", "html.parser")


SELECT_HTML = b"""\
<!DOCTYPE html>
<html>
<head><title>Select Page</title><script>var x = 1;</script></head>
<body>
  <h1>Heading One</h1>
  <p class="intro">Intro paragraph.</p>
  <ul><li><a href="https://example.com">A link</a></li></ul>
  <p>Outro paragraph.</p>
</body>
</html>
"""


class TestHtmlSelect:
    def test_single_match_no_title_prefix(self):
        result = processors[".html"](SELECT_HTML, select="h1")

        assert result["text"] == "# Heading One"  # a heading stays a heading
        assert "Select Page" not in result["text"]
        extra = result["meta"]["extra"]
        assert extra["selector"] == "h1"
        assert extra["selected_count"] == 1
        assert extra["title"] == "Select Page"  # title still recorded
        assert "select_note" not in extra
        assert extra["chars"] == len(result["text"])

    def test_multi_match_document_order(self):
        result = processors[".html"](SELECT_HTML, select="p")

        assert result["meta"]["extra"]["selected_count"] == 2
        text = result["text"]
        assert text.index("Intro paragraph.") < text.index("Outro paragraph.")
        assert "Heading One" not in text

    def test_comma_group_kwarg(self):
        result = processors[".html"](SELECT_HTML, select="h1, .intro")

        assert result["meta"]["extra"]["selected_count"] == 2
        assert "Heading One" in result["text"]
        assert "Intro paragraph." in result["text"]
        assert "Outro" not in result["text"]

    def test_comma_group_quoted_dsl_via_att(self, tmp_path):
        from attachments import att

        path = tmp_path / "page.html"
        path.write_bytes(SELECT_HTML)

        arts = att(f'{path}[select: "h1, .intro"]')
        assert len(arts) == 1
        extra = arts[0]["meta"]["extra"]
        assert extra["selector"] == "h1, .intro"
        assert extra["selected_count"] == 2
        assert "Heading One" in arts[0]["text"]
        assert "Outro" not in arts[0]["text"]

    def test_attribute_selector_kwarg(self):
        result = processors[".html"](SELECT_HTML, select="a[href]")

        assert result["meta"]["extra"]["selected_count"] == 1
        assert result["text"] == "A link"

    def test_attribute_selector_dsl_balanced_brackets(self, tmp_path):
        from attachments import att

        path = tmp_path / "page.html"
        path.write_bytes(SELECT_HTML)

        arts = att(f"{path}[select: a[href]]")
        assert arts[0]["meta"]["extra"]["selector"] == "a[href]"
        assert arts[0]["meta"]["extra"]["selected_count"] == 1
        assert arts[0]["text"] == "A link"

    def test_zero_match_not_an_error(self):
        result = processors[".html"](SELECT_HTML, select=".nope")

        assert result["text"] == ""
        extra = result["meta"]["extra"]
        assert extra["selected_count"] == 0
        assert extra["select_note"] == "selector matched no elements"
        assert "error" not in result["meta"]

    def test_invalid_selector_not_an_error(self):
        result = processors[".html"](SELECT_HTML, select="li:::")

        assert result["text"] == ""
        extra = result["meta"]["extra"]
        assert extra["selected_count"] == 0
        assert extra["select_note"].startswith("invalid selector:")
        assert "error" not in result["meta"]

    def test_css_alias(self):
        from attachments._options import get_options, resolve_options

        schema = get_options(".html")
        kwargs, warnings = resolve_options(schema, {"css": "h1"}, context=".html")
        assert kwargs == {"select": "h1"}
        assert warnings == []

        result = processors[".html"](SELECT_HTML, **kwargs)
        assert result["text"] == "# Heading One"

    def test_select_with_images_only_inside_selection(self):
        html = (
            b"<html><body>"
            b'<div id="keep"><img src="data:image/png;base64,'
            + _TINY_PNG.encode()
            + b'"/></div>'
            b'<div id="drop"><img src="data:image/gif;base64,'
            + _TINY_PNG.encode()
            + b'"/></div>'
            b"</body></html>"
        )
        result = processors[".html"](html, select="#keep", images=True)
        assert len(result["images"]) == 1
        assert result["images"][0]["mimetype"] == "image/png"

        result_all = processors[".html"](html, images=True)
        assert len(result_all["images"]) == 2

    def test_select_strips_whitespace(self):
        result = processors[".html"](SELECT_HTML, select="  h1  ")

        assert result["meta"]["extra"]["selector"] == "h1"
        assert result["meta"]["extra"]["selected_count"] == 1

    def test_empty_string_select_is_no_select(self):
        result = processors[".html"](SELECT_HTML, select="   ")

        extra = result["meta"]["extra"]
        assert "selector" not in extra
        assert "selected_count" not in extra
        # No-select path: the page has its own <h1>, so no title prefix
        assert result["text"].startswith("# Heading One")
        assert "Select Page" not in result["text"]

    def test_options_registration(self):
        from attachments._options import get_options

        for ext in (".html", ".htm"):
            names = sorted(o.name for o in get_options(ext))
            assert names == [
                "image_format",
                "images",
                "links",
                "main",
                "max_dim",
                "max_screens",
                "quality",
                "screenshot",
                "select",
                "url",
            ]


# Missing-dependency behavior is covered by the always-runnable tests in
# tests/test_processors/test_missing_deps.py (this module is skipped
# entirely when bs4 is absent, so such tests could never run here).


# ---------------------------------------------------------------------------
# Web-page behaviour: title, links/url, JS note, option validation
# ---------------------------------------------------------------------------


class TestHtmlPage:
    def test_title_not_prefixed_when_page_has_h1(self):
        html = b"<title>Site - Page</title><h1>Page</h1><p>Body.</p>"
        assert processors[".html"](html)["text"] == "# Page\n\nBody."

    def test_url_resolves_relative_links(self):
        html = b"<p><a href='intro.html'>Intro</a></p>"
        result = processors[".html"](
            html, links=True, url="https://docs.example.com/guide/"
        )
        assert result["text"] == "[Intro](https://docs.example.com/guide/intro.html)"
        assert result["meta"]["extra"]["url"] == "https://docs.example.com/guide/"
        assert result["meta"]["extra"]["links"] is True

    def test_base_href_wins_and_resolves_against_url(self):
        html = b"<head><base href='/v2/'></head><p><a href='a'>A</a></p>"
        result = processors[".html"](html, links=True, url="https://x.org/v1/page")
        assert result["text"] == "[A](https://x.org/v2/a)"

    def test_extra_records_content_scope(self):
        html = b"<body><nav>n</nav><main><p>Body text here.</p></main></body>"
        assert processors[".html"](html)["meta"]["extra"]["content"] == "main"
        assert (
            processors[".html"](html, main=False)["meta"]["extra"]["content"] == "page"
        )

    def test_javascript_shell_page_gets_a_note(self):
        html = (
            b"<html><head><title>App</title><script src='app.js'></script></head>"
            b"<body><div id='root'></div></body></html>"
        )
        result = processors[".html"](html)
        assert "JavaScript" in result["meta"]["note"]
        assert "screenshot: true" in result["meta"]["note"]

    def test_no_note_for_pages_with_text(self):
        html = b"<script>x()</script><p>" + b"Real content. " * 20 + b"</p>"
        assert "note" not in processors[".html"](html)["meta"]

    @pytest.mark.parametrize(
        ("options", "fragment"),
        [
            ({"max_screens": -1}, "max_screens"),
            ({"max_screens": True}, "max_screens"),
            ({"image_format": "gif"}, "image_format"),
            ({"quality": 0}, "quality"),
            ({"url": 5}, "url"),
        ],
    )
    def test_invalid_options_are_typed_errors(self, options, fragment):
        result = processors[".html"](SIMPLE_HTML, **options)
        error = result["meta"]["error"]
        assert error["code"] == "invalid-option"
        assert fragment in error["message"]
        assert result["meta"]["kind"] == "html"

    def test_screenshot_without_playwright_is_missing_dependency(self, monkeypatch):
        from attachments import deps
        from attachments.types import is_missing_dependency

        real = deps.check_dep

        def fake(feature):
            status = real(feature)
            if feature == "browser":
                return status._replace(available=False)
            return status

        monkeypatch.setattr("attachments._processors.html.check_dep", fake)
        result = processors[".html"](SIMPLE_HTML, screenshot=True)
        assert is_missing_dependency(result)
        assert "attachments[browser]" in result["meta"]["error"]["message"]
        assert "playwright install chromium" in result["meta"]["error"]["message"]

    def test_deeply_nested_markup_does_not_crash(self):
        html = b"<div>" * 3000 + b"deep words" + b"</div>" * 3000
        result = processors[".html"](html)
        assert "deep words" in result["text"]
        assert "error" not in result["meta"]
