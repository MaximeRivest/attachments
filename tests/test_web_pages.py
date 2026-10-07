"""End-to-end: web pages through ``att()`` (real HTTP on 127.0.0.1).

Pins what changed for URLs: the artifact is known by its address, the page
gets its address as the html ``url`` option (relative links resolve after
redirects), the server's Content-Type decides HTML vs. file, and source
warnings reach ``meta.warnings``.
"""

from __future__ import annotations

import pytest

from attachments import att
from attachments.deps import check_dep

pytestmark = pytest.mark.skipif(
    not check_dep("html").available, reason="beautifulsoup4 / lxml not installed"
)

PAGE = """<!doctype html><html><head><title>Guide - Example Docs</title></head>
<body>
<nav><a href="/">Home</a> <a href="/about">About</a></nav>
<main>
  <h1>Guide</h1>
  <p>Start with the <a href="intro.html">introduction</a>, then read
  <a href="/api">the API reference</a>.</p>
  <pre><code class="language-python">import example
example.run()</code></pre>
</main>
<footer>(c) Example</footer>
</body></html>"""


def test_web_page_is_markdown_main_content_known_by_url(http_server):
    url = http_server.route("/docs/guide", PAGE)
    [a] = att(url)
    assert a["meta"]["source"] == url
    assert a["meta"]["kind"] == "html"
    assert a["text"] == (
        "# Guide\n\n"
        "Start with the introduction, then read the API reference.\n\n"
        "```python\nimport example\nexample.run()\n```"
    )
    # The prompt names the page by its address, not "download"/"index.html".
    assert att(url).text.startswith(f"## {url}\n# Guide")


def test_links_resolve_against_the_final_url(http_server):
    final = http_server.route("/docs/", PAGE)
    start = http_server.redirect("/docs", final)
    [a] = att(f"{start}[links: true]")
    assert a["meta"]["source"] == final
    assert f"[introduction]({http_server.url('/docs/intro.html')})" in a["text"]
    assert f"[the API reference]({http_server.url('/api')})" in a["text"]


def test_explicit_url_option_wins(http_server):
    url = http_server.route("/p", PAGE)
    [a] = att(url, links=True, url="https://mirror.example.org/docs/")
    assert "(https://mirror.example.org/docs/intro.html)" in a["text"]


def test_whole_page_on_request(http_server):
    url = http_server.route("/p", PAGE)
    [a] = att(f"{url}[main: false]")
    assert "Home" in a["text"] and "(c) Example" in a["text"]


def test_html_served_for_a_file_name_is_read_as_html_with_warning(http_server):
    url = http_server.route("/o/r/blob/main/README.md", PAGE)
    [a] = att(url)
    assert a["meta"]["kind"] == "html"
    assert "<html" not in a["text"]
    assert a["meta"]["extra"]["filename"] == "README.md.html"
    assert any("web page" in w for w in a["meta"]["warnings"])


def test_non_html_downloads_get_no_url_option_warning(http_server):
    url = http_server.route("/notes.txt", "plain notes", content_type="text/plain")
    [a] = att(url)
    assert a["text"] == "plain notes"
    assert a["meta"]["source"] == url
    assert "warnings" not in a["meta"]


def test_local_files_keep_their_name_as_source(tmp_path):
    page = tmp_path / "page.html"
    page.write_text(PAGE)
    [a] = att(str(page))
    assert a["meta"]["source"] == "page.html"
    assert "url" not in a["meta"]["extra"]


def test_service_receives_the_page_url(http_server, monkeypatch):
    from attachments import core
    from attachments.types import make_artifact

    seen: dict = {}

    def fake_service(filename, data, api_key, *, options=None):
        seen.update(options or {})
        return make_artifact(text="from service", meta={"kind": "html"})

    monkeypatch.setattr(core, "_process_via_service", fake_service)
    url = http_server.route("/p", PAGE)
    [a] = att(url, api_key="k", prefer="service-only")
    assert a["text"] == "from service"
    assert seen["url"] == url
