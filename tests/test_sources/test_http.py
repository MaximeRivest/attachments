"""
Tests for HTTP(S) sources - download helpers and the SSRF guard.

=============================================================================
TEST GUIDELINES FOR HTTP SOURCES
=============================================================================

GOOD tests for HTTP sources:
    - Test filename extraction (Content-Disposition parsing)
    - Test the SSRF guard (private/loopback/metadata addresses blocked)
    - Mock urllib so no real network I/O happens

BAD tests for HTTP sources:
    - Making real HTTP requests (use mocking or skip)
    - Testing archive expansion here (that's test_archives.py)

=============================================================================
"""

from __future__ import annotations

import pytest

import attachments._sources.http as http_mod
from attachments._sources import unpack
from attachments._sources._guards import _assert_public_http_url
from attachments._sources.http import _filename_from_content_disposition


class TestFilenameFromContentDisposition:
    """Tests for _filename_from_content_disposition."""

    def test_simple_filename(self):
        result = _filename_from_content_disposition('attachment; filename="report.pdf"')
        assert result == "report.pdf"

    def test_unquoted_filename(self):
        result = _filename_from_content_disposition("attachment; filename=data.csv")
        assert result == "data.csv"

    def test_none_returns_none(self):
        assert _filename_from_content_disposition(None) is None

    def test_empty_returns_none(self):
        assert _filename_from_content_disposition("") is None

    def test_no_filename_in_header(self):
        result = _filename_from_content_disposition("attachment")
        assert result is None


class TestSsrfGuard:
    """_assert_public_http_url blocks private/internal addresses."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/admin",
            "http://localhost:8080/x",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.5/internal",
            "http://192.168.1.1/router",
            "http://[::1]/v6-loopback",
        ],
    )
    def test_blocks_non_public_addresses(self, url: str):
        with pytest.raises(ValueError, match="Blocked URL|Cannot resolve"):
            _assert_public_http_url(url)

    def test_blocks_non_http_schemes(self):
        with pytest.raises(ValueError, match="scheme"):
            _assert_public_http_url("ftp://example.com/file")

    def test_allows_public_literal_address(self):
        # 93.184.216.34 (example.com) is a public address; no DNS needed.
        _assert_public_http_url("http://93.184.216.34/page")

    def test_unpack_blocks_private_url_when_enabled(self):
        with pytest.raises(ValueError, match="non-public address"):
            unpack("http://127.0.0.1:9/secret.zip", block_private_urls=True)

    def test_guard_off_by_default_for_library_use(self, monkeypatch):
        """Without the flag, private URLs reach the downloader (no SSRF
        validation) — the library trusts its local caller by default."""
        seen = {}

        def fake_urlopen(req, timeout=None):
            seen["url"] = req.full_url
            raise OSError("stop before any network I/O")

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        with pytest.raises(OSError, match="stop before"):
            http_mod._download_http_or_https("http://127.0.0.1:9/x")
        assert seen["url"] == "http://127.0.0.1:9/x"


# =============================================================================
# Content-Type vs filename, SourceFile provenance (real local HTTP server)
# =============================================================================


class TestDownloadNamingAndProvenance:
    """The name agrees with the declared type; the final URL travels along."""

    def test_html_page_with_file_extension_is_named_html(self, http_server):
        url = http_server.route("/repo/blob/main/README.md", "<h1>Readme</h1>")
        [f] = unpack(url)
        name, data = f
        assert name == "README.md.html"
        assert data == b"<h1>Readme</h1>"
        assert f.url == url
        assert len(f.warnings) == 1
        assert "web page" in f.warnings[0] and ".md" in f.warnings[0]

    def test_bare_root_is_index_html(self, http_server):
        http_server.route("/", "<p>home</p>")
        [f] = unpack(http_server.url("/"))
        assert f.name == "index.html"
        assert f.warnings == ()

    def test_redirect_target_is_the_url(self, http_server):
        final = http_server.route("/docs/", "<p>docs</p>")
        start = http_server.redirect("/docs", final)
        [f] = unpack(start)
        assert f.url == final  # relative links must resolve against /docs/

    def test_pdf_without_extension_gets_one_silently(self, http_server):
        url = http_server.route(
            "/pdf/1706.03762", b"%PDF-1.4 x", content_type="application/pdf"
        )
        [f] = unpack(url)
        assert f.name == "1706.03762.pdf"
        assert f.warnings == ()

    def test_generic_types_never_override_the_name(self, http_server):
        http_server.route("/data.csv", "a,b\n1,2\n", content_type="text/plain")
        http_server.route("/nb.ipynb", "{}", content_type="application/json")
        http_server.route("/blob", b"\x00", content_type="application/octet-stream")
        assert unpack(http_server.url("/data.csv"))[0].name == "data.csv"
        assert unpack(http_server.url("/nb.ipynb"))[0].name == "nb.ipynb"
        assert unpack(http_server.url("/blob"))[0].name == "blob"

    def test_dynamic_pages_become_html_without_warning(self, http_server):
        [f] = unpack(http_server.route("/index.php", "<p>x</p>"))
        assert f.name == "index.php.html"
        assert f.warnings == ()

    def test_content_disposition_name_still_checked(self, http_server):
        url = http_server.route(
            "/dl",
            "<p>login required</p>",
            headers={"Content-Disposition": 'attachment; filename="report.pdf"'},
        )
        [f] = unpack(url)
        assert f.name == "report.pdf.html"
        assert ".pdf" in f.warnings[0]

    def test_archives_still_expand(self, http_server, sample_zip_bytes):
        url = http_server.route(
            "/bundle.zip", sample_zip_bytes, content_type="application/zip"
        )
        names = [name for name, _ in unpack(url)]
        assert names and all(n.startswith("bundle.zip/") for n in names)

    def test_github_blob_warning_names_the_raw_file(self):
        name, warning = http_mod._name_for_content_type(
            "app.py",
            "text/html; charset=utf-8",
            "https://github.com/o/r/blob/main/src/app.py",
        )
        assert name == "app.py.html"
        assert "https://raw.githubusercontent.com/o/r/main/src/app.py" in warning


class TestSourceFile:
    def test_is_a_plain_pair(self):
        import pickle

        from attachments._sources import SourceFile

        f = SourceFile("a.html", b"x", url="https://a.org/", warnings=["w"])
        assert f == ("a.html", b"x")
        assert list(f) == ["a.html", b"x"]
        copy = pickle.loads(pickle.dumps(f))
        assert copy == f and copy.url == "https://a.org/" and copy.warnings == ("w",)
