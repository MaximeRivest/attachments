from __future__ import annotations

import base64

import pytest

from attachments.config import configure
from attachments.service import (
    ServiceError,
    check_service_health,
    process_via_service,
    unpack_via_service,
)


class _DummyResponse:
    def __init__(
        self, *, status_code: int = 200, payload: dict | None = None, text: str = ""
    ):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class _DummyHttpx:
    class TimeoutException(Exception):
        pass

    class RequestError(Exception):
        pass

    def __init__(self):
        self.next_post: _DummyResponse | Exception | None = None
        self.next_get: _DummyResponse | Exception | None = None
        self.last_post: dict | None = None
        self.last_get: dict | None = None

    def post(self, url, **kwargs):
        self.last_post = {"url": url, "kwargs": kwargs}
        if isinstance(self.next_post, Exception):
            raise self.next_post
        return self.next_post or _DummyResponse(payload={})

    def get(self, url, **kwargs):
        self.last_get = {"url": url, "kwargs": kwargs}
        if isinstance(self.next_get, Exception):
            raise self.next_get
        return self.next_get or _DummyResponse(payload={"status": "ok"})


@pytest.fixture
def dummy_httpx(monkeypatch):
    stub = _DummyHttpx()
    monkeypatch.setattr("attachments.service._get_client", lambda: stub)
    return stub


class TestProcessViaService:
    def test_requires_api_key(self, dummy_httpx):
        configure(api_key=None)
        with pytest.raises(ServiceError, match="No API key"):
            process_via_service(b"hello", filename="a.txt")

    def test_success_decodes_images(self, dummy_httpx):
        configure(api_key="key", service_url="http://svc", timeout=7)
        img = base64.b64encode(b"img-bytes").decode("ascii")
        dummy_httpx.next_post = _DummyResponse(
            payload={
                "text": "ok",
                "images": [{"name": "p1.png", "bytes_b64": img}],
                "audio": [],
                "video": [],
                "meta": {},
            }
        )

        out = process_via_service(b"hello", filename="a.txt", options={"page_start": 1})

        assert out["text"] == "ok"
        assert out["images"][0]["bytes"] == b"img-bytes"
        assert "bytes_b64" not in out["images"][0]
        assert dummy_httpx.last_post["url"] == "http://svc/process"
        assert (
            dummy_httpx.last_post["kwargs"]["headers"]["Authorization"] == "Bearer key"
        )

    def test_option_types_survive_wire_encoding(self, dummy_httpx):
        """Every option value is JSON-encoded so the server's json.loads
        round-trips the exact parsed type: a quoted DSL string like '3'
        stays a string and never becomes the integer 3 (dsl-grammar rule 1),
        and 'null' stays a string instead of decoding to None."""
        import json

        configure(api_key="key", service_url="http://svc")
        dummy_httpx.next_post = _DummyResponse(payload={"text": "ok"})

        process_via_service(
            b"hello",
            filename="data.xlsx",
            options={
                "sheet": "3",  # quoted DSL string
                "rows": 3,  # integer
                "pages": (1, 4),  # DSL range tuple
                "images": True,  # boolean
                "title": "null",  # quoted DSL string
                "skipped": None,  # None options are dropped
            },
        )

        form = dummy_httpx.last_post["kwargs"]["data"]
        assert json.loads(form["sheet"]) == "3"
        assert json.loads(form["rows"]) == 3
        assert json.loads(form["pages"]) == [1, 4]
        assert json.loads(form["images"]) is True
        assert json.loads(form["title"]) == "null"
        assert "skipped" not in form

    @pytest.mark.parametrize(
        "status,expected",
        [
            (401, "Invalid API key"),
            (402, "API quota exceeded"),
            (413, "File too large"),
        ],
    )
    def test_common_status_codes(self, dummy_httpx, status: int, expected: str):
        configure(api_key="key", service_url="http://svc")
        dummy_httpx.next_post = _DummyResponse(
            status_code=status, payload={"error": "x"}
        )

        with pytest.raises(ServiceError, match=expected):
            process_via_service(b"hello")

    def test_other_http_error_uses_error_field(self, dummy_httpx):
        configure(api_key="key", service_url="http://svc")
        dummy_httpx.next_post = _DummyResponse(
            status_code=500, payload={"error": "boom"}
        )

        with pytest.raises(ServiceError, match="Service error: boom"):
            process_via_service(b"hello")

    def test_timeout_wrapped(self, dummy_httpx):
        configure(api_key="key", timeout=3)
        dummy_httpx.next_post = _DummyHttpx.TimeoutException("slow")

        with pytest.raises(ServiceError, match="timed out"):
            process_via_service(b"hello")

    def test_request_error_wrapped(self, dummy_httpx):
        configure(api_key="key")
        dummy_httpx.next_post = _DummyHttpx.RequestError("network")

        with pytest.raises(ServiceError, match="request failed"):
            process_via_service(b"hello")


class TestUnpackViaService:
    def test_success_decodes_files(self, dummy_httpx):
        configure(api_key="key", service_url="http://svc")
        data_b64 = base64.b64encode(b"payload").decode("ascii")
        dummy_httpx.next_post = _DummyResponse(
            payload={"files": [{"filename": "a.txt", "data_b64": data_b64}]}
        )

        files = unpack_via_service("https://example.com")

        assert files == [("a.txt", b"payload")]
        assert dummy_httpx.last_post["url"] == "http://svc/unpack"

    def test_http_error_raises_service_error(self, dummy_httpx):
        configure(api_key="key", service_url="http://svc")
        dummy_httpx.next_post = _DummyResponse(
            status_code=500, payload={"error": "bad unpack"}
        )

        with pytest.raises(ServiceError, match="bad unpack"):
            unpack_via_service("https://example.com")


class TestCheckServiceHealth:
    def test_returns_json_on_success(self, dummy_httpx):
        configure(service_url="http://svc")
        dummy_httpx.next_get = _DummyResponse(
            payload={"status": "ok", "version": "0.1.0"}
        )

        out = check_service_health()

        assert out["status"] == "ok"
        assert dummy_httpx.last_get["url"] == "http://svc/health"

    def test_returns_error_dict_on_failure(self, dummy_httpx):
        configure(service_url="http://svc")
        dummy_httpx.next_get = Exception("boom")

        out = check_service_health()

        assert out["status"] == "error"
        assert "boom" in out["error"]
