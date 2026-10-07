"""Tests for html ``screenshot: true`` (headless Chromium via Playwright).

Skipped unless Playwright is installed AND a Chromium can be launched
(``playwright install chromium``, or ``ATTACHMENTS_CHROMIUM`` pointing at
an executable). Everything is served from 127.0.0.1: no internet.
"""

from __future__ import annotations

import asyncio
import io
import os

import pytest

from attachments._processors import processors
from attachments.deps import check_dep

# The autouse conftest fixture scrubs ATTACHMENTS_* variables (they can hold
# API keys); the browser location is plain configuration, so keep it.
_CHROMIUM = os.environ.get("ATTACHMENTS_CHROMIUM")


@pytest.fixture(autouse=True)
def _keep_chromium_location(monkeypatch):
    if _CHROMIUM:
        monkeypatch.setenv("ATTACHMENTS_CHROMIUM", _CHROMIUM)


def _browser_ready() -> bool:
    if not (check_dep("browser").available and check_dep("html").available):
        return False
    if _CHROMIUM:
        os.environ["ATTACHMENTS_CHROMIUM"] = _CHROMIUM
    from attachments._processors._browser import BrowserUnavailable, capture_screens

    try:
        capture_screens(html="<p>probe</p>", max_screens=1)
    except BrowserUnavailable:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _browser_ready(), reason="Playwright with a launchable Chromium not available"
)

# 2000 CSS px tall -> 3 screens of 800 (800, 800, 400).
TALL_PAGE = (
    "<html><head><title>Tall</title><style>body,p{margin:0}"
    ".b{height:500px;background:#3a6}</style></head><body>"
    + "".join(f"<div class='b'><p>Block {i}</p></div>" for i in range(4))
    + "</body></html>"
)


def _size(data: bytes) -> tuple[int, int]:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as img:
        return img.size


def test_url_page_is_captured_as_screens(http_server):
    url = http_server.route("/tall", TALL_PAGE)
    result = processors[".html"](TALL_PAGE.encode(), screenshot=True, url=url)
    shots = result["images"]
    assert [s["name"] for s in shots] == [
        "page.html-screen-1.png",
        "page.html-screen-2.png",
        "page.html-screen-3.png",
    ]
    assert [_size(s["bytes"]) for s in shots] == [(1280, 800), (1280, 800), (1280, 400)]
    info = result["meta"]["extra"]["screenshot"]
    assert info["loaded_from"] == "url"
    assert info["screens"] == info["screens_total"] == 3
    assert "Block 0" in result["text"]  # text is unaffected


def test_max_screens_caps_from_the_top(http_server):
    url = http_server.route("/tall", TALL_PAGE)
    result = processors[".html"](
        TALL_PAGE.encode(), screenshot=True, url=url, max_screens=1
    )
    assert len(result["images"]) == 1
    info = result["meta"]["extra"]["screenshot"]
    assert info["screens"] == 1 and info["screens_total"] == 3


def test_jpeg_and_max_dim(http_server):
    url = http_server.route("/tall", TALL_PAGE)
    result = processors[".html"](
        TALL_PAGE.encode(),
        screenshot=True,
        url=url,
        max_screens=1,
        image_format="jpeg",
        quality=60,
        max_dim=640,
    )
    [shot] = result["images"]
    assert shot["mimetype"] == "image/jpeg"
    assert shot["name"].endswith(".jpg")
    assert _size(shot["bytes"]) == (640, 400)


def test_local_html_is_rendered_from_its_bytes(http_server):
    # No url: the document itself is rendered; <base> still loads images.
    http_server.route("/img/pixel.png", _PNG, content_type="image/png")
    html = (
        f"<html><head><base href='{http_server.url('/')}'></head>"
        "<body><p>Local</p><img src='img/pixel.png'></body></html>"
    )
    result = processors[".html"](html.encode(), screenshot=True)
    assert result["meta"]["extra"]["screenshot"]["loaded_from"] == "html"
    assert len(result["images"]) == 1
    assert "/img/pixel.png" in http_server.requests


def test_ssrf_guard_blocks_private_pages(http_server):
    from attachments._sources._guards import private_url_guard

    url = http_server.route("/secret", "<p>internal admin page</p>")
    with private_url_guard(True):
        result = processors[".html"](b"<p>text</p>", screenshot=True, url=url)
    assert result["images"] == []
    assert any(w.startswith("screenshot failed") for w in result["meta"]["warnings"])
    assert result["text"] == "text"  # the text survives a failed screenshot
    assert "/secret" not in http_server.requests


def test_ssrf_guard_blocks_private_subresources(http_server):
    from attachments._sources._guards import private_url_guard

    http_server.route("/track.png", _PNG, content_type="image/png")
    html = f"<p>public page</p><img src='{http_server.url('/track.png')}'>"
    with private_url_guard(True):
        result = processors[".html"](html.encode(), screenshot=True)
    assert len(result["images"]) == 1  # the page itself renders
    assert "/track.png" not in http_server.requests


def test_works_inside_a_running_event_loop(http_server):
    # Jupyter runs an asyncio loop; Playwright's sync API refuses to run in
    # one, so the browser must run on its own thread.
    url = http_server.route("/tall", TALL_PAGE)

    async def inside_loop():
        return processors[".html"](
            TALL_PAGE.encode(), screenshot=True, url=url, max_screens=1
        )

    result = asyncio.run(inside_loop())
    assert len(result["images"]) == 1


def test_via_att_dsl(http_server):
    from attachments import att

    url = http_server.route("/tall", TALL_PAGE)
    [a] = att(f"{url}[screenshot: true, max_screens: 2]")
    assert a["meta"]["source"] == url
    assert len(a["images"]) == 2
    assert a["images"][0]["name"] == "tall.html-screen-1.png"


_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
    b"\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
    b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)
