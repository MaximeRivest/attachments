"""Self-hosted attachments server.

Run a local server with all processors available, allowing other machines
to use attachments without installing dependencies.

Usage:
    # On server machine (has all deps installed):
    pip install attachments[all-local]
    python -m attachments.server --host 0.0.0.0 --port 8000

    # On client machines (zero deps needed):
    pip install attachments[service]

    from attachments import att, configure
    configure(service_url="http://server-ip:8000", api_key="team-secret")
    artifacts = att("document.pdf")  # Processed on server

The server provides:
    POST /process  - Process a file
    POST /unpack   - Unpack a URL/path
    GET  /health   - Health check with available processors
    GET  /formats  - List supported formats
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any

# Server deps are optional
try:
    import urllib.parse
    from http.server import BaseHTTPRequestHandler, HTTPServer
except ImportError:
    HTTPServer = None  # type: ignore
    BaseHTTPRequestHandler = object  # type: ignore

log = logging.getLogger("attachments.server")


def _make_handler():
    """Build the ``BaseHTTPRequestHandler`` subclass.

    This is an internal helper shared by :func:`create_app` (WSGI wrapper)
    and :func:`run_server` (stdlib ``HTTPServer``).
    """
    # Import here to avoid circular imports
    from .deps import check_deps
    from .processors import processors

    class AttachmentsHandler(BaseHTTPRequestHandler):
        """HTTP handler for attachments server."""

        # Configurable via environment
        API_KEY = os.environ.get("ATTACHMENTS_SERVER_KEY", "")
        MAX_UPLOAD_SIZE = int(
            os.environ.get("ATTACHMENTS_MAX_UPLOAD", str(256 * 1024 * 1024))
        )

        def _check_auth(self) -> bool:
            """Check API key if configured."""
            if not self.API_KEY:
                return True  # No auth required

            auth = self.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token = auth[7:]
                return token == self.API_KEY
            return False

        def _send_json(self, data: dict, status: int = 200):
            """Send JSON response."""
            body = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_error(self, message: str, status: int = 400):
            """Send error response."""
            self._send_json({"error": message}, status)

        def _parse_multipart(self) -> tuple[bytes, str, dict]:
            """Parse multipart form data. Returns (file_bytes, filename, fields)."""
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                raise ValueError("Expected multipart/form-data")

            # Extract boundary
            boundary = None
            for part in content_type.split(";"):
                part = part.strip()
                if part.startswith("boundary="):
                    boundary = part[9:].strip('"')
                    break

            if not boundary:
                raise ValueError("No boundary in multipart data")

            # Read body
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > self.MAX_UPLOAD_SIZE:
                raise ValueError(f"Upload too large (max {self.MAX_UPLOAD_SIZE})")

            body = self.rfile.read(content_length)

            # Parse parts (simple implementation)
            boundary_bytes = f"--{boundary}".encode()
            parts = body.split(boundary_bytes)

            file_data = b""
            filename = "file"
            fields: dict[str, str] = {}

            for part in parts:
                if not part or part == b"--\r\n" or part == b"--":
                    continue

                # Split headers from content
                if b"\r\n\r\n" in part:
                    headers_raw, content = part.split(b"\r\n\r\n", 1)
                    headers_str = headers_raw.decode("utf-8", errors="replace")

                    # Remove trailing \r\n from content
                    if content.endswith(b"\r\n"):
                        content = content[:-2]

                    # Check if it's a file or field
                    if 'filename="' in headers_str:
                        file_data = content
                        # Extract filename
                        for line in headers_str.split("\r\n"):
                            if 'filename="' in line:
                                start = line.index('filename="') + 10
                                end = line.index('"', start)
                                filename = line[start:end]
                                break
                    elif 'name="' in headers_str:
                        # Regular field
                        for line in headers_str.split("\r\n"):
                            if 'name="' in line:
                                start = line.index('name="') + 6
                                end = line.index('"', start)
                                field_name = line[start:end]
                                fields[field_name] = content.decode(
                                    "utf-8", errors="replace"
                                )
                                break

            return file_data, filename, fields

        def do_GET(self):
            """Handle GET requests."""
            parsed = urllib.parse.urlparse(self.path)

            if parsed.path == "/health":
                deps = check_deps()
                self._send_json(
                    {
                        "status": "ok",
                        "version": "0.1.0",
                        "features": {k: v for k, v in deps.items() if v},
                    }
                )

            elif parsed.path == "/formats":
                self._send_json(
                    {
                        "formats": list(processors.keys()),
                        "count": len(processors),
                    }
                )

            else:
                self._send_error("Not found", 404)

        def do_POST(self):
            """Handle POST requests."""
            if not self._check_auth():
                self._send_error("Unauthorized", 401)
                return

            parsed = urllib.parse.urlparse(self.path)

            if parsed.path == "/process":
                self._handle_process()

            elif parsed.path == "/unpack":
                self._handle_unpack()

            else:
                self._send_error("Not found", 404)

        def _handle_process(self):
            """Process uploaded file."""
            try:
                file_data, filename, fields = self._parse_multipart()
                log.debug("process request: %s (%d bytes)", filename, len(file_data))

                if not file_data:
                    self._send_error("No file uploaded")
                    return

                # Build options from fields
                options: dict[str, Any] = {}
                for key, value in fields.items():
                    # Try to parse as JSON for complex values
                    try:
                        options[key] = json.loads(value)
                    except json.JSONDecodeError:
                        options[key] = value

                # Process with local-only mode
                from .core import _process_single

                artifact = _process_single(
                    filename,
                    file_data,
                    prefer="local-only",
                    **options,
                )

                # Encode images as base64 for JSON transport
                if artifact.get("images"):
                    for img in artifact["images"]:
                        if "bytes" in img and isinstance(img["bytes"], bytes):
                            img["bytes_b64"] = base64.b64encode(img["bytes"]).decode(
                                "ascii"
                            )
                            del img["bytes"]

                self._send_json(artifact)

            except ValueError as e:
                self._send_error(str(e), 400)
            except Exception as e:
                log.exception("processing failed for uploaded file")
                self._send_error(f"Processing failed: {e}", 500)

        def _handle_unpack(self):
            """Unpack a URL."""
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                data = json.loads(body)

                url = data.get("url")
                if not url:
                    self._send_error("Missing 'url' in request body")
                    return

                from .unpack import unpack

                files = unpack(url)

                # Encode file contents as base64
                result = {
                    "files": [
                        {
                            "filename": fname,
                            "data_b64": base64.b64encode(fdata).decode("ascii"),
                        }
                        for fname, fdata in files
                    ]
                }

                self._send_json(result)

            except json.JSONDecodeError:
                self._send_error("Invalid JSON", 400)
            except Exception as e:
                log.exception("unpack failed")
                self._send_error(f"Unpack failed: {e}", 500)

        def log_message(self, format: str, *args):
            """Route stdlib HTTP server logs through the logging module."""
            log.info("%s %s %s", args[0], args[1], args[2])

    return AttachmentsHandler


def create_app():
    """Create a WSGI application for production deployment.

    Compatible with **gunicorn**, **uWSGI**, and any PEP-3333 server::

        gunicorn "attachments.server:create_app()" -b 0.0.0.0:8000 -w 4

    Returns:
        A PEP-3333 WSGI callable ``(environ, start_response) -> Iterable[bytes]``.
    """
    handler_cls = _make_handler()

    # Import the same deps the handler uses at class scope
    from .deps import check_deps
    from .processors import processors

    def wsgi_app(environ, start_response):
        """Minimal WSGI adapter that delegates to AttachmentsHandler."""
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/")

        # Build a JSON response helper
        def _json_response(data: dict, status: int = 200):
            body = json.dumps(data).encode("utf-8")
            status_line = f"{status} {_STATUS_PHRASES.get(status, 'OK')}"
            start_response(
                status_line,
                [
                    ("Content-Type", "application/json"),
                    ("Content-Length", str(len(body))),
                ],
            )
            return [body]

        def _error(msg: str, status: int = 400):
            return _json_response({"error": msg}, status)

        # --- GET routes ---
        if method == "GET":
            if path == "/health":
                deps = check_deps()
                return _json_response(
                    {
                        "status": "ok",
                        "version": "0.1.0",
                        "features": {k: v for k, v in deps.items() if v},
                    }
                )
            if path == "/formats":
                return _json_response(
                    {
                        "formats": list(processors.keys()),
                        "count": len(processors),
                    }
                )
            return _error("Not found", 404)

        # --- Auth check for POST ---
        api_key = os.environ.get("ATTACHMENTS_SERVER_KEY", "")
        if api_key:
            auth = environ.get("HTTP_AUTHORIZATION", "")
            if not (auth.startswith("Bearer ") and auth[7:] == api_key):
                return _error("Unauthorized", 401)

        if method != "POST":
            return _error("Method not allowed", 405)

        # Read body once
        try:
            content_length = int(environ.get("CONTENT_LENGTH", 0))
        except (ValueError, TypeError):
            content_length = 0
        body = environ["wsgi.input"].read(content_length)

        # --- POST /process ---
        if path == "/process":
            content_type = environ.get("CONTENT_TYPE", "")
            if "multipart/form-data" not in content_type:
                return _error("Expected multipart/form-data")

            # Reuse the handler's multipart parser via a shim
            try:
                file_data, filename, fields = _parse_multipart_raw(
                    body, content_type, handler_cls.MAX_UPLOAD_SIZE
                )
            except ValueError as exc:
                return _error(str(exc))

            if not file_data:
                return _error("No file uploaded")

            options: dict[str, Any] = {}
            for key, value in fields.items():
                try:
                    options[key] = json.loads(value)
                except json.JSONDecodeError:
                    options[key] = value

            from .core import _process_single

            try:
                artifact = _process_single(
                    filename, file_data, prefer="local-only", **options
                )
            except Exception as exc:
                log.exception("processing failed for uploaded file")
                return _error(f"Processing failed: {exc}", 500)

            if artifact.get("images"):
                import base64 as b64mod

                for img in artifact["images"]:
                    if "bytes" in img and isinstance(img["bytes"], bytes):
                        img["bytes_b64"] = b64mod.b64encode(
                            img["bytes"]
                        ).decode("ascii")
                        del img["bytes"]

            return _json_response(artifact)

        # --- POST /unpack ---
        if path == "/unpack":
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                return _error("Invalid JSON")

            url = data.get("url")
            if not url:
                return _error("Missing 'url' in request body")

            from .unpack import unpack as _unpack

            try:
                files = _unpack(url)
            except Exception as exc:
                log.exception("unpack failed")
                return _error(f"Unpack failed: {exc}", 500)

            result = {
                "files": [
                    {
                        "filename": fname,
                        "data_b64": base64.b64encode(fdata).decode("ascii"),
                    }
                    for fname, fdata in files
                ]
            }
            return _json_response(result)

        return _error("Not found", 404)

    return wsgi_app


# HTTP status phrase lookup used by the WSGI adapter
_STATUS_PHRASES: dict[int, str] = {
    200: "OK",
    400: "Bad Request",
    401: "Unauthorized",
    404: "Not Found",
    405: "Method Not Allowed",
    413: "Payload Too Large",
    500: "Internal Server Error",
}


def _parse_multipart_raw(
    body: bytes, content_type: str, max_size: int
) -> tuple[bytes, str, dict[str, str]]:
    """Standalone multipart parser (no handler instance needed)."""
    if "multipart/form-data" not in content_type:
        raise ValueError("Expected multipart/form-data")

    boundary = None
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("boundary="):
            boundary = part[9:].strip('"')
            break
    if not boundary:
        raise ValueError("No boundary in multipart data")

    if len(body) > max_size:
        raise ValueError(f"Upload too large (max {max_size})")

    boundary_bytes = f"--{boundary}".encode()
    parts = body.split(boundary_bytes)

    file_data = b""
    filename = "file"
    fields: dict[str, str] = {}

    for raw_part in parts:
        if not raw_part or raw_part in (b"--\r\n", b"--"):
            continue
        if b"\r\n\r\n" not in raw_part:
            continue
        headers_raw, content = raw_part.split(b"\r\n\r\n", 1)
        headers_str = headers_raw.decode("utf-8", errors="replace")
        if content.endswith(b"\r\n"):
            content = content[:-2]

        if 'filename="' in headers_str:
            file_data = content
            for line in headers_str.split("\r\n"):
                if 'filename="' in line:
                    start = line.index('filename="') + 10
                    end = line.index('"', start)
                    filename = line[start:end]
                    break
        elif 'name="' in headers_str:
            for line in headers_str.split("\r\n"):
                if 'name="' in line:
                    start = line.index('name="') + 6
                    end = line.index('"', start)
                    field_name = line[start:end]
                    fields[field_name] = content.decode("utf-8", errors="replace")
                    break

    return file_data, filename, fields


def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Run the attachments server.

    Args:
        host: Host to bind to (0.0.0.0 for all interfaces)
        port: Port to listen on

    Environment Variables:
        ATTACHMENTS_SERVER_KEY: API key for authentication (optional)
        ATTACHMENTS_MAX_UPLOAD: Max upload size in bytes (default 256MB)
    """
    handler = _make_handler()
    server = HTTPServer((host, port), handler)

    api_key = os.environ.get("ATTACHMENTS_SERVER_KEY", "")
    auth_status = "enabled" if api_key else "disabled (set ATTACHMENTS_SERVER_KEY)"

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                   Attachments Server                         ║
╠══════════════════════════════════════════════════════════════╣
║  URL:  http://{host}:{port:<5}                                 ║
║  Auth: {auth_status:<52} ║
╠══════════════════════════════════════════════════════════════╣
║  Endpoints:                                                  ║
║    POST /process  - Process a file                           ║
║    POST /unpack   - Unpack a URL                             ║
║    GET  /health   - Health check                             ║
║    GET  /formats  - List supported formats                   ║
╚══════════════════════════════════════════════════════════════╝
""")

    # Show available processors
    from .deps import check_deps

    deps = check_deps()
    available = [k for k, v in deps.items() if v]
    print(f"Available features: {', '.join(available)}")
    print()
    print("Press Ctrl+C to stop")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run a self-hosted attachments server")
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on (default: 8000)",
    )

    args = parser.parse_args()
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
