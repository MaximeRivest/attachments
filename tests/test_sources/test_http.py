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
