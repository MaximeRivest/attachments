from __future__ import annotations

import base64
import json
import threading
import uuid
from http.client import HTTPConnection
from http.server import HTTPServer
from pathlib import Path

import pytest

from attachments import register_processor
from attachments.core import _process_single
from attachments.server import _make_handler, create_app
from attachments.types import make_artifact, missing_dep_artifact


def _build_multipart_body(
    *,
    field_name: str,
    filename: str,
    content: bytes,
    fields: dict[str, str] | None = None,
):
    boundary = f"----attachments-{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    for key, value in (fields or {}).items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
        chunks.append(str(value).encode())
        chunks.append(b"\r\n")

    chunks.append(f"--{boundary}\r\n".encode())
    chunks.append(
        (
            f'Content-Disposition: form-data; name="{field_name}"; '
            f'filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
    )
    chunks.append(content)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())

    body = b"".join(chunks)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


@pytest.fixture
def live_server(monkeypatch):
    monkeypatch.delenv("ATTACHMENTS_SERVER_KEY", raising=False)
    monkeypatch.delenv("ATTACHMENTS_MAX_UPLOAD", raising=False)

    handler = _make_handler()
    httpd = HTTPServer(("127.0.0.1", 0), handler)
    host, port = httpd.server_address

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    try:
        yield host, port
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)


def _request_json(
    host: str,
    port: int,
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
):
    conn = HTTPConnection(host, port, timeout=5)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        payload = resp.read().decode("utf-8")
        return resp.status, json.loads(payload)
    finally:
        conn.close()


class TestServerEndpoints:
    def test_health_and_formats(self, live_server):
        host, port = live_server

        status, health = _request_json(host, port, "GET", "/health")
        assert status == 200
        assert health["status"] == "ok"
        assert isinstance(health["features"], dict)

        status, formats = _request_json(host, port, "GET", "/formats")
        assert status == 200
        assert formats["count"] >= 1
        assert ".txt" in formats["formats"]

    def test_options_endpoint(self, live_server):
        host, port = live_server

        status, schema = _request_json(host, port, "GET", "/options")
        assert status == 200
        assert schema["version"] == 1
        assert any(o["name"] == "pages" for o in schema["processors"][".pdf"])
        assert any(o["name"] == "ref" for o in schema["sources"]["github://"])

    def test_process_multipart_success(self, live_server):
        host, port = live_server
        body, content_type = _build_multipart_body(
            field_name="file",
            filename="note.txt",
            content=b"hello from server test",
            fields={"page_start": "1"},
        )

        status, payload = _request_json(
            host,
            port,
            "POST",
            "/process",
            body=body,
            headers={"Content-Type": content_type, "Content-Length": str(len(body))},
        )

        assert status == 200
        assert "hello from server test" in payload["text"]
        assert payload["meta"]["source"] == "note.txt"
        assert payload["meta"]["extra"]["filename"] == "note.txt"

    def test_unpack_success(self, live_server, tmp_path: Path):
        host, port = live_server
        p = tmp_path / "hello.txt"
        p.write_bytes(b"hello")

        body = json.dumps({"url": str(p)}).encode("utf-8")
        status, payload = _request_json(
            host,
            port,
            "POST",
            "/unpack",
            body=body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )

        assert status == 200
        assert payload["files"][0]["filename"] == "hello.txt"
        assert base64.b64decode(payload["files"][0]["data_b64"]) == b"hello"

    def test_unpack_invalid_json(self, live_server):
        host, port = live_server

        status, payload = _request_json(
            host,
            port,
            "POST",
            "/unpack",
            body=b"not-json",
            headers={"Content-Type": "application/json", "Content-Length": "8"},
        )

        assert status == 400
        assert "Invalid JSON" in payload["error"]


class TestServerAuthAndLimits:
    def test_requires_bearer_when_key_set(self, monkeypatch):
        monkeypatch.setenv("ATTACHMENTS_SERVER_KEY", "secret")
        handler = _make_handler()
        httpd = HTTPServer(("127.0.0.1", 0), handler)
        host, port = httpd.server_address
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        try:
            body, content_type = _build_multipart_body(
                field_name="file",
                filename="a.txt",
                content=b"hello",
            )
            status, payload = _request_json(
                host,
                port,
                "POST",
                "/process",
                body=body,
                headers={
                    "Content-Type": content_type,
                    "Content-Length": str(len(body)),
                },
            )
            assert status == 401
            assert "Unauthorized" in payload["error"]

            status, payload = _request_json(
                host,
                port,
                "POST",
                "/process",
                body=body,
                headers={
                    "Content-Type": content_type,
                    "Content-Length": str(len(body)),
                    "Authorization": "Bearer secret",
                },
            )
            assert status == 200
            assert "hello" in payload["text"]
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=3)

    def test_upload_too_large(self, monkeypatch):
        monkeypatch.setenv("ATTACHMENTS_MAX_UPLOAD", "10")
        handler = _make_handler()
        httpd = HTTPServer(("127.0.0.1", 0), handler)
        host, port = httpd.server_address
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        try:
            body, content_type = _build_multipart_body(
                field_name="file",
                filename="big.txt",
                content=b"x" * 64,
            )
            status, payload = _request_json(
                host,
                port,
                "POST",
                "/process",
                body=body,
                headers={
                    "Content-Type": content_type,
                    "Content-Length": str(len(body)),
                },
            )

            assert status == 400
            assert "Upload too large" in payload["error"]
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=3)


class TestCoreFallbackModes:
    def test_local_success_does_not_call_service(self, monkeypatch):
        called = {"service": False}

        @register_processor(".foo")
        def _local_ok(data: bytes, **_opts):
            return make_artifact(text="local")

        def _no_service(*args, **kwargs):
            called["service"] = True
            return make_artifact(text="service")

        monkeypatch.setattr("attachments.service.process_via_service", _no_service)

        out = _process_single("a.foo", b"x", prefer="local", api_key="k")
        assert out["text"] == "local"
        assert called["service"] is False

    def test_local_missing_dep_falls_back_to_service(self, monkeypatch):
        @register_processor(".miss")
        def _local_missing(data: bytes, **_opts):
            return missing_dep_artifact("a.miss", "pdf")

        def _service_ok(data: bytes, **_opts):
            return make_artifact(text="from service")

        monkeypatch.setattr("attachments.service.process_via_service", _service_ok)

        out = _process_single("a.miss", b"x", prefer="local", api_key="k")
        assert out["text"] == "from service"
        assert out["meta"].get("via") == "service"

    def test_service_mode_falls_back_to_local_on_service_failure(self, monkeypatch):
        @register_processor(".bar")
        def _local_ok(data: bytes, **_opts):
            return make_artifact(text="local fallback")

        def _boom(*_args, **_kwargs):
            raise RuntimeError("service down")

        monkeypatch.setattr("attachments.core._process_via_service", _boom)

        out = _process_single("a.bar", b"x", prefer="service", api_key="k")
        assert out["text"] == "local fallback"

    def test_local_exception_uses_service_when_key_present(self, monkeypatch):
        @register_processor(".err")
        def _local_raises(data: bytes, **_opts):
            raise RuntimeError("boom")

        def _service_ok(data: bytes, **_opts):
            return make_artifact(text="saved by service")

        monkeypatch.setattr("attachments.service.process_via_service", _service_ok)

        out = _process_single("a.err", b"x", prefer="local", api_key="k")
        assert out["text"] == "saved by service"
        assert out["meta"]["via"] == "service"


class TestWsgiApp:
    """Tests for the WSGI-compatible create_app()."""

    @pytest.fixture
    def app(self, monkeypatch):
        monkeypatch.delenv("ATTACHMENTS_SERVER_KEY", raising=False)
        monkeypatch.delenv("ATTACHMENTS_MAX_UPLOAD", raising=False)
        return create_app()

    @staticmethod
    def _call(app, method, path, *, body=b"", headers=None):
        """Minimal WSGI environ builder + caller."""
        import io as _io

        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": _io.BytesIO(body),
        }
        for k, v in (headers or {}).items():
            key = "HTTP_" + k.upper().replace("-", "_")
            if k.lower() == "content-type":
                key = "CONTENT_TYPE"
            environ[key] = v

        captured: dict = {}

        def start_response(status, response_headers):
            captured["status"] = status
            captured["headers"] = response_headers

        chunks = app(environ, start_response)
        payload = b"".join(chunks)
        return captured["status"], json.loads(payload)

    def test_health(self, app):
        status, body = self._call(app, "GET", "/health")
        assert status.startswith("200")
        assert body["status"] == "ok"

    def test_formats(self, app):
        status, body = self._call(app, "GET", "/formats")
        assert status.startswith("200")
        assert ".txt" in body["formats"]

    def test_options(self, app):
        status, body = self._call(app, "GET", "/options")
        assert status.startswith("200")
        assert body["version"] == 1
        assert any(o["name"] == "sheet" for o in body["processors"][".xlsx"])

    def test_process_text(self, app):
        raw, ct = _build_multipart_body(
            field_name="file",
            filename="hi.txt",
            content=b"wsgi works",
        )
        status, body = self._call(
            app,
            "POST",
            "/process",
            body=raw,
            headers={"Content-Type": ct},
        )
        assert status.startswith("200")
        assert "wsgi works" in body["text"]

    def test_auth_required(self, monkeypatch):
        monkeypatch.setenv("ATTACHMENTS_SERVER_KEY", "s3cret")
        app = create_app()

        raw, ct = _build_multipart_body(
            field_name="file", filename="a.txt", content=b"hi"
        )
        status, body = self._call(
            app, "POST", "/process", body=raw, headers={"Content-Type": ct}
        )
        assert status.startswith("401")

        status, body = self._call(
            app,
            "POST",
            "/process",
            body=raw,
            headers={"Content-Type": ct, "Authorization": "Bearer s3cret"},
        )
        assert status.startswith("200")
        assert "hi" in body["text"]

    def test_unpack(self, app, tmp_path):
        p = tmp_path / "wsgi.txt"
        p.write_bytes(b"wsgi-unpack")
        raw = json.dumps({"url": str(p)}).encode()
        status, body = self._call(
            app,
            "POST",
            "/unpack",
            body=raw,
            headers={"Content-Type": "application/json"},
        )
        assert status.startswith("200")
        assert body["files"][0]["filename"] == "wsgi.txt"

    def test_not_found(self, app):
        status, body = self._call(app, "GET", "/nope")
        assert status.startswith("404")
