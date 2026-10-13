"""LightOnOCR as an OCR engine (attachments._processors._lighton).

The engine is tested against a stand-in vLLM server: a real HTTP server on
a TCP port or a unix socket, answering chat completions the way vLLM does,
so the request, the transport and the fallback to RapidOCR are exercised
end to end. The real model is checked by deploy/lambda/smoke.py.
"""

from __future__ import annotations

import base64
import io
import json
import socket
import socketserver
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from attachments._processors import _lighton, processors
from attachments._processors.image import image_processor
from attachments.config import reset_config
from attachments.deps import check_dep, clear_cache
from attachments.types import ERROR_INVALID_OPTION, ERROR_PROCESSING

pytestmark = pytest.mark.skipif(
    not (check_dep("pdf-images").available and check_dep("image").available),
    reason="PyMuPDF and Pillow needed for the page fixtures",
)

RAPIDOCR = check_dep("ocr").available

GROUNDED = (
    "![header](0,0,999,40) Journal of Testing, vol. 3\n"
    "![title](80,60,900,90) Results\n"
    "![text](80,100,900,300) The samples were read twice.\n"
    "![page_number](480,960,520,980) 12"
)


# ---------------------------------------------------------------------------
# A stand-in vLLM server
# ---------------------------------------------------------------------------


class FakeVllm:
    """Answers POST /v1/chat/completions; records every request."""

    def __init__(self):
        self.requests: list[dict] = []
        self.content = GROUNDED
        self.finish_reason = "stop"
        self.status = 200
        #: per-request override: n-th request (1-based) -> finish_reason
        self.finish_by_call: dict[int, str] = {}
        self._lock = threading.Lock()

    def handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # quiet
                pass

            def address_string(self):  # unix sockets have no (host, port)
                return "local"

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                with fake._lock:
                    fake.requests.append({"path": self.path, "body": body})
                    n = len(fake.requests)
                if fake.status >= 400:
                    data = b'{"error": "boom"}'
                    self.send_response(fake.status)
                else:
                    finish = fake.finish_by_call.get(n, fake.finish_reason)
                    data = json.dumps(
                        {
                            "choices": [
                                {
                                    "message": {"content": fake.content},
                                    "finish_reason": finish,
                                }
                            ]
                        }
                    ).encode()
                    self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        return Handler

    def image(self, n: int = 0):
        """The picture sent in request *n*, as a PIL image."""
        from PIL import Image

        url = self.requests[n]["body"]["messages"][0]["content"][0]["image_url"]["url"]
        return Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))


class _UnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


class _TcpHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True


@pytest.fixture
def fake_tcp(monkeypatch):
    fake = FakeVllm()
    server = _TcpHTTPServer(("127.0.0.1", 0), fake.handler())
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv(_lighton.URL_ENV, f"http://127.0.0.1:{server.server_port}/v1")
    monkeypatch.delenv(_lighton.MODEL_ENV, raising=False)
    yield fake
    server.shutdown()
    server.server_close()


@pytest.fixture
def fake_unix(monkeypatch, tmp_path):
    fake = FakeVllm()
    path = tmp_path / "vllm.sock"
    server = _UnixHTTPServer(str(path), fake.handler())
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv(_lighton.URL_ENV, f"unix:{path}")
    monkeypatch.delenv(_lighton.MODEL_ENV, raising=False)
    yield fake
    server.shutdown()
    server.server_close()


@pytest.fixture
def nothing_listening(monkeypatch, tmp_path):
    """An endpoint that refuses: a socket path where nobody listens."""
    monkeypatch.setenv(_lighton.URL_ENV, f"unix:{tmp_path / 'absent.sock'}")


@pytest.fixture(autouse=True)
def clean_config(monkeypatch):
    monkeypatch.delenv("ATTACHMENTS_OCR_ENGINE", raising=False)
    reset_config()
    yield
    reset_config()


@pytest.fixture
def no_rapidocr(monkeypatch):
    monkeypatch.setitem(sys.modules, "rapidocr", None)
    clear_cache()
    yield
    clear_cache()


# ---------------------------------------------------------------------------
# Fixtures: scans with real words (RapidOCR must find text when it stands in)
# ---------------------------------------------------------------------------


def _scan_pdf(pages: int = 1, size=(612, 792)) -> bytes:
    """An image-only PDF: each page a picture of the words PAGE <n> READ."""
    import pymupdf

    out = pymupdf.open()
    for n in range(pages):
        src = pymupdf.open()
        page = src.new_page(width=size[0], height=size[1])
        page.insert_text((72, 144), f"PAGE {n + 1} READ", fontsize=40)
        pix = page.get_pixmap(dpi=150, colorspace=pymupdf.csGRAY)
        dst = out.new_page(width=size[0], height=size[1])
        dst.insert_image(dst.rect, stream=pix.tobytes("png"))
    return out.tobytes()


def _text_png() -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (600, 200), "white")
    try:
        font = ImageFont.load_default(size=60)
    except TypeError:
        font = ImageFont.load_default()
    ImageDraw.Draw(img).text((20, 60), "HELLO WORLD 42", fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def pdf(data: bytes, **options):
    return processors[".pdf"](data, filename="scan.pdf", **options)


# ---------------------------------------------------------------------------
# PDF pages
# ---------------------------------------------------------------------------


class TestPdfPages:
    def test_reads_page_as_markdown_without_margins(self, fake_tcp):
        result = pdf(_scan_pdf(), ocr=True, ocr_engine="lighton")

        assert "error" not in result["meta"]
        assert result["text"] == "# Results\n\nThe samples were read twice."
        extra = result["meta"]["extra"]
        assert extra["ocr_backend"] == "lighton"
        assert extra["ocr_model"] == "lightonai/LightOnOCR-3-0.8B"
        assert "ocr_engine_fallback" not in extra
        assert "warnings" not in result["meta"]

    def test_request_follows_the_benchmarked_settings(self, fake_tcp):
        pdf(_scan_pdf(), ocr=True, ocr_engine="lighton")

        request = fake_tcp.requests[0]
        assert request["path"] == "/v1/chat/completions"
        body = request["body"]
        assert body["model"] == "lightonai/LightOnOCR-3-0.8B"
        assert body["temperature"] == 0.1
        assert body["top_p"] == 1.0
        assert body["seed"] == 0
        assert body["max_tokens"] == _lighton.MAX_TOKENS
        assert body["chat_template_kwargs"] == {"enable_thinking": False}
        content = body["messages"][0]["content"]
        assert content[0]["type"] == "image_url"
        assert content[1] == {"type": "text", "text": "grounding"}

    def test_page_drawn_as_large_as_five_megapixels(self, fake_tcp):
        pdf(_scan_pdf(), ocr=True, ocr_engine="lighton")  # US letter

        width, height = fake_tcp.image().size
        assert 4_800_000 < width * height <= _lighton.MAX_PIXELS
        assert abs(width / height - 612 / 792) < 0.01

    def test_over_a_unix_socket(self, fake_unix):
        result = pdf(_scan_pdf(), ocr=True, ocr_engine="lighton")

        assert result["text"] == "# Results\n\nThe samples were read twice."
        assert len(fake_unix.requests) == 1

    def test_every_page_in_order(self, fake_tcp):
        result = pdf(_scan_pdf(pages=3), ocr=True, ocr_engine="lighton")

        assert len(fake_tcp.requests) == 3
        assert result["meta"]["extra"]["ocr_pages"] == [1, 2, 3]

    def test_older_generation_reads_plainly(self, fake_tcp, monkeypatch):
        monkeypatch.setenv(_lighton.MODEL_ENV, "lightonai/LightOnOCR-2-1B")
        fake_tcp.content = "plain **markdown** page"

        result = pdf(_scan_pdf(), ocr=True, ocr_engine="lighton")

        content = fake_tcp.requests[0]["body"]["messages"][0]["content"]
        assert len(content) == 1  # the picture alone, no grounding prompt
        assert result["text"] == "plain **markdown** page"


@pytest.mark.skipif(not RAPIDOCR, reason="rapidocr stands in for LightOn here")
class TestRapidOcrStandsIn:
    def test_endpoint_down_rapidocr_reads_every_page(self, nothing_listening):
        result = pdf(_scan_pdf(pages=2), ocr=True, ocr_engine="lighton")

        assert "error" not in result["meta"]
        assert "PAGE 1 READ" in result["text"] and "PAGE 2 READ" in result["text"]
        extra = result["meta"]["extra"]
        assert extra["ocr_backend"] == "rapidocr"
        assert extra["ocr_engine_fallback"] == "rapidocr"
        assert extra["ocr_fallback_pages"] == [1, 2]
        [warning] = result["meta"]["warnings"]
        assert "LightOnOCR could not read 2 of the 2 pages" in warning
        assert "RapidOCR read them instead" in warning

    def test_unfinished_page_alone_is_read_by_rapidocr(self, fake_tcp):
        fake_tcp.finish_by_call = {1: "length"}  # the first request never ends

        result = pdf(_scan_pdf(pages=2), ocr=True, ocr_engine="lighton")

        extra = result["meta"]["extra"]
        assert extra["ocr_backend"] == "lighton"
        assert len(extra["ocr_fallback_pages"]) == 1
        assert "did not finish the page" in result["meta"]["warnings"][0]
        assert "The samples were read twice." in result["text"]

    def test_server_error_falls_back(self, fake_tcp):
        fake_tcp.status = 500

        result = pdf(_scan_pdf(), ocr=True, ocr_engine="lighton")

        assert "PAGE 1 READ" in result["text"]
        assert "HTTP 500" in result["meta"]["warnings"][0]

    def test_unreachable_endpoint_is_asked_once(self, tmp_path):
        """After a refusal, later pages go straight to RapidOCR."""
        calls = []

        def fallback(image):
            calls.append(image)
            from attachments._processors._ocr import OcrText

            return OcrText("from rapidocr")

        where = _lighton.endpoint(f"unix:{tmp_path / 'absent.sock'}")
        reader = _lighton.Reader(where, fallback)
        from PIL import Image

        picture = Image.new("RGB", (10, 10), "white")
        for page in (1, 2, 3):
            assert reader(picture, page).text == "from rapidocr"
        assert reader.unreachable and "cannot reach" in reader.unreachable
        assert sorted(reader.fell_back) == [1, 2, 3]


class TestWithoutRapidOcr:
    def test_endpoint_failure_is_a_processing_error(self, fake_tcp, no_rapidocr):
        fake_tcp.status = 500

        result = pdf(_scan_pdf(), ocr=True, ocr_engine="lighton")

        error = result["meta"]["error"]
        assert error["code"] == ERROR_PROCESSING
        assert "LightOn OCR request failed" in error["message"]
        assert "running and reachable" in error["message"]


# ---------------------------------------------------------------------------
# Choosing the engine
# ---------------------------------------------------------------------------


class TestEngineChoice:
    def test_configured_default_is_used_when_the_request_names_none(
        self, fake_tcp, monkeypatch
    ):
        monkeypatch.setenv("ATTACHMENTS_OCR_ENGINE", "lighton")

        result = pdf(_scan_pdf(), ocr=True)

        assert result["meta"]["extra"]["ocr_backend"] == "lighton"
        assert len(fake_tcp.requests) == 1

    def test_named_engine_wins_over_the_default(self, fake_tcp, monkeypatch):
        monkeypatch.setenv("ATTACHMENTS_OCR_ENGINE", "lighton")

        result = pdf(_scan_pdf(), ocr=True, ocr_engine="rapidocr")

        assert fake_tcp.requests == []
        assert result["meta"]["extra"].get("ocr_backend") in ("rapidocr", None)

    @pytest.mark.skipif(not RAPIDOCR, reason="rapidocr reads instead")
    def test_configured_default_without_endpoint_is_quietly_rapidocr(self, monkeypatch):
        monkeypatch.setenv("ATTACHMENTS_OCR_ENGINE", "lighton")
        monkeypatch.delenv(_lighton.URL_ENV, raising=False)

        result = pdf(_scan_pdf(), ocr=True)

        assert "error" not in result["meta"]
        assert result["meta"]["extra"]["ocr_backend"] == "rapidocr"
        assert result["meta"]["extra"]["ocr_engine_fallback"] == "rapidocr"

    def test_named_lighton_without_endpoint_is_invalid(self, monkeypatch):
        monkeypatch.delenv(_lighton.URL_ENV, raising=False)

        result = pdf(_scan_pdf(), ocr=True, ocr_engine="lighton")

        error = result["meta"]["error"]
        assert error["code"] == ERROR_INVALID_OPTION
        assert "ATTACHMENTS_LIGHTON_URL" in error["message"]
        assert "SERVER capability" in error["message"]

    def test_bad_configured_engine_is_refused(self, monkeypatch):
        monkeypatch.setenv("ATTACHMENTS_OCR_ENGINE", "tesseract")

        with pytest.raises(ValueError, match="expected rapidocr or lighton"):
            pdf(_scan_pdf(), ocr=True)

    def test_unknown_named_engine_is_invalid(self):
        result = pdf(_scan_pdf(), ocr=True, ocr_engine="bogus")

        assert result["meta"]["error"]["code"] == ERROR_INVALID_OPTION


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------


class TestImages:
    def test_image_read_by_lighton(self, fake_unix):
        result = image_processor(
            _text_png(), filename="sign.png", ocr=True, ocr_engine="lighton"
        )

        assert result["text"] == "# Results\n\nThe samples were read twice."
        extra = result["meta"]["extra"]
        assert extra["ocr_backend"] == "lighton"
        assert extra["ocr_model"] == "lightonai/LightOnOCR-3-0.8B"

    @pytest.mark.skipif(not RAPIDOCR, reason="rapidocr stands in")
    def test_image_endpoint_down_rapidocr_reads(self, nothing_listening):
        result = image_processor(
            _text_png(), filename="sign.png", ocr=True, ocr_engine="lighton"
        )

        assert "HELLO" in result["text"]
        assert result["meta"]["extra"]["ocr_backend"] == "rapidocr"
        assert "RapidOCR read it instead" in result["meta"]["warnings"][0]

    def test_image_endpoint_down_without_rapidocr_is_an_error(
        self, nothing_listening, no_rapidocr
    ):
        result = image_processor(
            _text_png(), filename="sign.png", ocr=True, ocr_engine="lighton"
        )

        assert result["meta"]["error"]["code"] == ERROR_PROCESSING

    def test_large_picture_lowered_to_five_megapixels(self, fake_tcp):
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (4000, 3000), "white").save(buf, format="PNG")

        image_processor(
            buf.getvalue(), filename="big.png", ocr=True, ocr_engine="lighton"
        )

        width, height = fake_tcp.image().size
        assert width * height <= _lighton.MAX_PIXELS
        assert abs(width / height - 4 / 3) < 0.01


def test_socket_path_forms():
    assert _lighton.endpoint("unix:/a/b.sock").socket_path == "/a/b.sock"
    assert _lighton.endpoint("unix:///a/b.sock").socket_path == "/a/b.sock"
    assert _lighton.endpoint("http://h:1/v1").socket_path is None
    assert Path(_lighton.endpoint("unix:/x").socket_path).is_absolute()
    assert socket.AF_UNIX  # unix sockets exist where these tests run
