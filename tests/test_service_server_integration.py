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
        import attachments

        host, port = live_server

        status, health = _request_json(host, port, "GET", "/health")
        assert status == 200
        assert health["status"] == "ok"
        assert health["version"] == attachments.__version__
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

            assert status == 413
            assert "Upload too large" in payload["error"]
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=3)

    def test_unpack_upload_too_large(self, monkeypatch):
        """The cap applies to /unpack too — checked BEFORE reading the body."""
        monkeypatch.setenv("ATTACHMENTS_MAX_UPLOAD", "10")
        handler = _make_handler()
        httpd = HTTPServer(("127.0.0.1", 0), handler)
        host, port = httpd.server_address
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        try:
            body = json.dumps({"url": "x" * 256}).encode("utf-8")
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

            assert status == 413
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
        import attachments

        status, body = self._call(app, "GET", "/health")
        assert status.startswith("200")
        assert body["status"] == "ok"
        assert body["version"] == attachments.__version__

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

    def test_process_rejects_oversized_body_before_reading(self, monkeypatch):
        """WSGI path must enforce the cap from CONTENT_LENGTH, before read()."""
        monkeypatch.setenv("ATTACHMENTS_MAX_UPLOAD", "1024")
        app = create_app()

        class ExplodingInput:
            """Fails the test if the server buffers the oversized body."""

            def read(self, *_args):
                raise AssertionError("body must not be read when oversized")

        raw, ct = _build_multipart_body(
            field_name="file", filename="big.txt", content=b"x" * 4096
        )
        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/process",
            "CONTENT_LENGTH": str(len(raw)),
            "CONTENT_TYPE": ct,
            "wsgi.input": ExplodingInput(),
        }
        captured: dict = {}

        def start_response(status, headers):
            captured["status"] = status

        payload = b"".join(app(environ, start_response))
        assert captured["status"].startswith("413")
        assert "Upload too large" in json.loads(payload)["error"]

    def test_unpack_rejects_oversized_body_before_reading(self, monkeypatch):
        monkeypatch.setenv("ATTACHMENTS_MAX_UPLOAD", "1024")
        app = create_app()

        class ExplodingInput:
            def read(self, *_args):
                raise AssertionError("body must not be read when oversized")

        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/unpack",
            "CONTENT_LENGTH": str(2048),
            "CONTENT_TYPE": "application/json",
            "wsgi.input": ExplodingInput(),
        }
        captured: dict = {}

        def start_response(status, headers):
            captured["status"] = status

        payload = b"".join(app(environ, start_response))
        assert captured["status"].startswith("413")
        assert "Upload too large" in json.loads(payload)["error"]

    def test_unpack_bad_input_is_400_without_internals(self, app):
        """Unsupported input is a 4xx client error, not a leaky 500."""
        raw = json.dumps({"url": "/nonexistent/path/xyz"}).encode()
        status, body = self._call(
            app,
            "POST",
            "/unpack",
            body=raw,
            headers={"Content-Type": "application/json"},
        )
        assert status.startswith("400")
        assert "Unpack failed" not in body["error"]

    def test_unpack_internal_error_is_generic(self, app, monkeypatch):
        """Unexpected exceptions must not leak details to the client."""

        def _boom(*_args, **_kwargs):
            raise RuntimeError("secret /tmp/attachments_github_x path")

        monkeypatch.setattr("attachments._sources.unpack", _boom)
        raw = json.dumps({"url": "https://example.com/x.zip"}).encode()
        status, body = self._call(
            app,
            "POST",
            "/unpack",
            body=raw,
            headers={"Content-Type": "application/json"},
        )
        assert status.startswith("500")
        assert body["error"] == "Internal error"
        assert "secret" not in json.dumps(body)

    def test_unpack_blocks_private_urls_by_default(self, app):
        """SSRF guard: /unpack refuses loopback/metadata addresses."""
        raw = json.dumps({"url": "http://127.0.0.1:9/secret"}).encode()
        status, body = self._call(
            app,
            "POST",
            "/unpack",
            body=raw,
            headers={"Content-Type": "application/json"},
        )
        assert status.startswith("400")
        assert "non-public address" in body["error"]


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    import io as _io
    import zipfile

    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _tar_bytes(members: dict[str, bytes]) -> bytes:
    import io as _io
    import tarfile

    buf = _io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, content in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            tf.addfile(info, _io.BytesIO(content))
    return buf.getvalue()


class TestUnpackUploadedBytes:
    """POST /unpack with multipart archive bytes (httpx WSGITransport)."""

    @pytest.fixture
    def client(self, monkeypatch):
        httpx = pytest.importorskip("httpx")
        monkeypatch.delenv("ATTACHMENTS_SERVER_KEY", raising=False)
        monkeypatch.delenv("ATTACHMENTS_MAX_UPLOAD", raising=False)
        with httpx.Client(
            transport=httpx.WSGITransport(app=create_app()),
            base_url="http://testserver",
        ) as client:
            yield client

    def test_zip_bytes_round_trip(self, client):
        data = _zip_bytes({"a.txt": b"alpha", "dir/b.csv": b"x,y"})
        resp = client.post("/unpack", files={"file": ("bundle.zip", data)})

        assert resp.status_code == 200
        files = {
            f["filename"]: base64.b64decode(f["data_b64"]) for f in resp.json()["files"]
        }
        assert files == {"bundle.zip/a.txt": b"alpha", "bundle.zip/dir/b.csv": b"x,y"}

    def test_tar_bytes_round_trip(self, client):
        data = _tar_bytes({"notes.txt": b"tar payload"})
        resp = client.post("/unpack", files={"file": ("backup.tar", data)})

        assert resp.status_code == 200
        files = resp.json()["files"]
        assert files[0]["filename"] == "backup.tar/notes.txt"
        assert base64.b64decode(files[0]["data_b64"]) == b"tar payload"

    def test_zip_bomb_rejected(self, client, monkeypatch):
        import attachments._sources.archives as archives_mod

        monkeypatch.setattr(archives_mod, "MAX_ARCHIVE_EXPANSION_BYTES", 64)
        data = _zip_bytes({"big.bin": b"x" * 4096})
        resp = client.post("/unpack", files={"file": ("bomb.zip", data)})

        assert resp.status_code == 400
        assert "expansion" in resp.json()["error"].lower()

    def test_non_archive_bytes_400(self, client):
        resp = client.post("/unpack", files={"file": ("note.txt", b"just text")})

        assert resp.status_code == 400
        assert "not a supported archive" in resp.json()["error"]

    def test_oversize_content_length_413_without_body_read(self, monkeypatch):
        """The cap is enforced from CONTENT_LENGTH before any body read."""
        monkeypatch.setenv("ATTACHMENTS_MAX_UPLOAD", "16")
        app = create_app()

        class ExplodingInput:
            def read(self, *_args):
                raise AssertionError("body must not be read when oversized")

        raw, ct = _build_multipart_body(
            field_name="file",
            filename="big.zip",
            content=_zip_bytes({"a.txt": b"x" * 256}),
        )
        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/unpack",
            "CONTENT_LENGTH": str(len(raw)),
            "CONTENT_TYPE": ct,
            "wsgi.input": ExplodingInput(),
        }
        captured: dict = {}

        def start_response(status, headers):
            captured["status"] = status

        payload = b"".join(app(environ, start_response))
        assert captured["status"].startswith("413")
        assert "Upload too large" in json.loads(payload)["error"]

    def test_auth_required_when_key_set(self, monkeypatch):
        httpx = pytest.importorskip("httpx")
        monkeypatch.setenv("ATTACHMENTS_SERVER_KEY", "s3cret")
        data = _zip_bytes({"a.txt": b"hi"})
        with httpx.Client(
            transport=httpx.WSGITransport(app=create_app()),
            base_url="http://testserver",
        ) as client:
            resp = client.post("/unpack", files={"file": ("a.zip", data)})
            assert resp.status_code == 401

            resp = client.post(
                "/unpack",
                files={"file": ("a.zip", data)},
                headers={"Authorization": "Bearer s3cret"},
            )
            assert resp.status_code == 200
            assert resp.json()["files"][0]["filename"] == "a.zip/a.txt"

    def test_stdlib_handler_zip_bytes(self, live_server):
        """The stdlib BaseHTTPRequestHandler path supports multipart too."""
        host, port = live_server
        data = _zip_bytes({"inner.txt": b"stdlib path"})
        body, content_type = _build_multipart_body(
            field_name="file", filename="arch.zip", content=data
        )

        status, payload = _request_json(
            host,
            port,
            "POST",
            "/unpack",
            body=body,
            headers={"Content-Type": content_type, "Content-Length": str(len(body))},
        )

        assert status == 200
        assert payload["files"][0]["filename"] == "arch.zip/inner.txt"
        assert base64.b64decode(payload["files"][0]["data_b64"]) == b"stdlib path"


class TestVersionPrefixedRoutes:
    """The hosted default service_url ends in /v1; bare URLs do not.

    The server accepts both spellings of every route so either client
    configuration works (see _strip_api_version in server.py).
    """

    def test_wsgi_v1_health_and_process(self, tmp_path):
        import httpx

        from attachments.server import create_app

        client = httpx.Client(
            transport=httpx.WSGITransport(app=create_app()),
            base_url="http://testserver",
        )
        r = client.get("/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

        r = client.post(
            "/v1/process",
            files={"file": ("hello.txt", b"hello from v1 prefix")},
        )
        assert r.status_code == 200
        assert r.json()["text"] == "hello from v1 prefix"

    def test_wsgi_bare_routes_still_work(self):
        import httpx

        from attachments.server import create_app

        client = httpx.Client(
            transport=httpx.WSGITransport(app=create_app()),
            base_url="http://testserver",
        )
        assert client.get("/health").status_code == 200
        assert client.get("/v1/options").status_code == 200
        # Only the literal /v1 prefix is stripped
        assert client.get("/v123/health").status_code == 404
