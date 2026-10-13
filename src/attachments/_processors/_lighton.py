"""LightOnOCR as an OCR engine: one page picture in, Markdown out.

LightOnOCR is a vision-language model served by vLLM (an OpenAI-compatible
endpoint) — a server capability, not a pip install. The machine running
attachments points ``ATTACHMENTS_LIGHTON_URL`` at it:

- ``http://127.0.0.1:8830/v1``: an address;
- ``unix:/run/lighton-ocr/vllm.sock``: a local socket (vLLM ``--uds``). A
  sandboxed server that may open no local address can still reach the
  model this way.

Requests follow the settings behind LightOnOCR-3's published olmOCR-bench
results (LightOn's ``benchmarks/reproduce``), measured on lambda on
2026-10-12: 82.8 overall for LightOnOCR-3-0.8B (LightOn: 85.5), against
39.7 for attachments with RapidOCR:

- the page picture up to 5 megapixels (drawn at 400 dpi, then lowered);
- *grounding* mode: the model returns labelled layout blocks, so page
  headers, footers and page numbers can be dropped (74.9 when kept);
- temperature 0.1, top_p 1, thinking off. A fixed seed makes repeated
  reads of the same page agree (vLLM's batching can still change a rare
  token).

LightOnOCR-1 and -2 have no grounding mode: they get the picture alone and
their Markdown is returned as is.

A page the model does not finish within ``MAX_TOKENS`` tokens is a page it
got stuck repeating (0.1 % of the benchmark's pages); it counts as failed,
like an endpoint that does not answer, and the caller reads it with
RapidOCR instead (see :class:`Reader`).
"""

from __future__ import annotations

import base64
import http.client
import io
import json
import logging
import os
import re
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("attachments.ocr")

#: Environment variables configuring the engine.
URL_ENV = "ATTACHMENTS_LIGHTON_URL"
MODEL_ENV = "ATTACHMENTS_LIGHTON_MODEL"
DEFAULT_MODEL = "lightonai/LightOnOCR-3-0.8B"

#: Pictures larger than this are lowered before being sent (LightOn's rule).
MAX_PIXELS = 5_000_000
#: Page drawing resolution for this engine (then lowered to MAX_PIXELS).
DPI = 400
#: A page needing more output tokens than this is stuck repeating itself:
#: the longest real page of olmOCR-bench is ~13k characters (~4k tokens).
MAX_TOKENS = 8192
TEMPERATURE = 0.1
TOP_P = 1.0
SEED = 0
GROUNDING_PROMPT = "grounding"
#: Seconds to connect, and to wait for one page.
CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 100.0

#: Blocks dropped from the text: running headers and footers, page numbers,
#: margin notes. Footnotes stay (they belong to the page's content).
MARGIN_LABELS = frozenset(
    {
        "header",
        "footer",
        "page_number",
        "page_header",
        "page_footer",
        "header_image",
        "footer_image",
        "aside_text",
    }
)

#: ``![label](x1,y1,x2,y2)`` opens a block; its text runs to the next one.
#: A trailing ``+`` on the label marks a block continuing the previous one.
_MARKER = re.compile(
    r"!\[([A-Za-z_][\w-]*?)\+?\]\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)[ \t]*"
)
_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+")


class Unavailable(Exception):
    """The endpoint cannot be reached (refused, missing socket, timeout).

    Its message is for the person who sent the file (it lands in
    ``meta.warnings``); the technical detail goes to the log.
    """


class Incomplete(Exception):
    """The model stopped at MAX_TOKENS without finishing the page."""


@dataclass(frozen=True)
class Endpoint:
    """Where the model answers: an HTTP base URL, or a unix socket."""

    base: str  # e.g. "http://127.0.0.1:8830/v1"; "http://localhost/v1" for a socket
    socket_path: str | None = None

    @property
    def label(self) -> str:
        return f"unix:{self.socket_path}" if self.socket_path else self.base


def endpoint(url: str | None = None) -> Endpoint | None:
    """The configured endpoint, or None when ``ATTACHMENTS_LIGHTON_URL`` is unset.

    Examples:
        >>> endpoint("http://127.0.0.1:8830/v1/")
        Endpoint(base='http://127.0.0.1:8830/v1', socket_path=None)
        >>> endpoint("unix:/run/lighton-ocr/vllm.sock")
        Endpoint(base='http://localhost/v1', socket_path='/run/lighton-ocr/vllm.sock')
        >>> endpoint("unix:///run/lighton-ocr/vllm.sock").socket_path
        '/run/lighton-ocr/vllm.sock'
        >>> endpoint("") is None
        True
    """
    raw = (os.environ.get(URL_ENV, "") if url is None else url).strip()
    if not raw:
        return None
    if raw.startswith("unix:"):
        path = "/" + raw[len("unix:") :].lstrip("/")
        return Endpoint("http://localhost/v1", path)
    return Endpoint(raw.rstrip("/"))


def model_name() -> str:
    return os.environ.get(MODEL_ENV, "").strip() or DEFAULT_MODEL


def has_grounding(model: str) -> bool:
    """LightOnOCR-3 reads in grounding mode; generations 1 and 2 cannot.

    Examples:
        >>> has_grounding("lightonai/LightOnOCR-3-0.8B")
        True
        >>> has_grounding("lightonai/LightOnOCR-2-1B")
        False
        >>> has_grounding("lightonai/LightOnOCR-1B-1025")
        False
        >>> has_grounding("my-ocr")  # unknown names: the current generation
        True
    """
    name = model.lower()
    return not (re.search(r"lightonocr-[12]-", name) or "lightonocr-1b" in name)


# ---------------------------------------------------------------------------
# Transport: standard library only, over TCP or a unix socket
# ---------------------------------------------------------------------------


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float):
        super().__init__("localhost", timeout=timeout)
        self._path = path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(CONNECT_TIMEOUT)
        try:
            sock.connect(self._path)
        except BaseException:
            sock.close()
            raise
        sock.settimeout(self.timeout)
        self.sock = sock


class _TcpConnection(http.client.HTTPConnection):
    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), CONNECT_TIMEOUT)
        self.sock.settimeout(self.timeout)


class _TlsConnection(http.client.HTTPSConnection):
    def connect(self) -> None:
        sock = socket.create_connection((self.host, self.port), CONNECT_TIMEOUT)
        sock.settimeout(self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def post_json(where: Endpoint, path: str, payload: dict) -> dict:
    """POST *payload* to ``<base><path>``; the JSON answer.

    Raises :class:`Unavailable` when the endpoint cannot be reached and
    ``RuntimeError`` for an HTTP error status.
    """
    from urllib.parse import urlsplit

    parts = urlsplit(where.base + path)
    if where.socket_path:
        conn: http.client.HTTPConnection = _UnixConnection(
            where.socket_path, READ_TIMEOUT
        )
    elif parts.scheme == "https":
        conn = _TlsConnection(parts.hostname or "", parts.port, timeout=READ_TIMEOUT)
    else:
        conn = _TcpConnection(parts.hostname or "", parts.port, timeout=READ_TIMEOUT)
    body = json.dumps(payload).encode("utf-8")
    target = parts.path + (f"?{parts.query}" if parts.query else "")
    try:
        try:
            conn.request(
                "POST", target, body=body, headers={"Content-Type": "application/json"}
            )
        except (OSError, http.client.HTTPException) as e:
            log.warning("LightOn OCR: cannot reach %s: %s", where.label, e)
            raise Unavailable("its server is not running right now") from e
        try:
            response = conn.getresponse()
            data = response.read()
        except TimeoutError as e:
            log.warning("LightOn OCR: %s did not answer in time", where.label)
            raise Unavailable("its server did not answer in time") from e
        if response.status >= 400:
            log.warning(
                "LightOn OCR: HTTP %s from %s: %s",
                response.status,
                where.label,
                data[:300].decode("utf-8", "replace"),
            )
            raise RuntimeError(
                f"its server answered with an error (HTTP {response.status})"
            )
        return json.loads(data)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# One page
# ---------------------------------------------------------------------------


def prepare(image: Any) -> Any:
    """*image* as RGB, lowered to at most MAX_PIXELS."""
    from PIL import Image

    from .image import _ocr_input

    image = _ocr_input(image)
    pixels = image.width * image.height
    if pixels > MAX_PIXELS:
        scale = (MAX_PIXELS / pixels) ** 0.5
        size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
        image = image.resize(size, Image.Resampling.LANCZOS)
    return image


def to_markdown(raw: str) -> str:
    """Grounding output as Markdown, margin blocks dropped.

    Titles become ``#`` headings and formulas ``$$`` blocks, as LightOn
    renders them for its benchmark. Output without block markers is
    returned as is.

    Examples:
        >>> raw = (
        ...     "![header](0,0,999,40) Journal of Things 12\\n"
        ...     "![title](80,60,900,90) On reading\\n"
        ...     "![text](80,100,900,300) First paragraph.\\n"
        ...     "![formula](80,310,900,340) $$E = mc^2$$\\n"
        ...     "![page_number](480,960,520,980) 7"
        ... )
        >>> print(to_markdown(raw))
        # On reading
        <BLANKLINE>
        First paragraph.
        <BLANKLINE>
        $$
        E = mc^2
        $$
        >>> to_markdown("plain text, no blocks")
        'plain text, no blocks'
    """
    marks = list(_MARKER.finditer(raw))
    if not marks:
        return raw.strip()
    parts: list[str] = []
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(raw)
        label = mark.group(1).lower()
        text = raw[mark.end() : end].strip()
        if label in MARGIN_LABELS or not text:
            continue
        if label == "title" and not _HEADING.match(text):
            text = f"# {text}"
        elif label == "formula":
            text = f"$$\n{_strip_formula(text)}\n$$"
        parts.append(text)
    return "\n\n".join(parts)


def _strip_formula(text: str) -> str:
    for delimiter in ("$$", "$"):
        if (
            len(text) > 2 * len(delimiter)
            and text.startswith(delimiter)
            and text.endswith(delimiter)
        ):
            inner = text[len(delimiter) : -len(delimiter)]
            if "$" not in inner and inner.strip():
                return inner.strip()
    return text


def read(image: Any, where: Endpoint, model: str | None = None) -> str:
    """Markdown of one page picture. Raises Unavailable, Incomplete, RuntimeError."""
    model = model or model_name()
    picture = prepare(image)
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG")
    url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    grounding = has_grounding(model)
    content: list[dict] = [{"type": "image_url", "image_url": {"url": url}}]
    if grounding:
        content.append({"type": "text", "text": GROUNDING_PROMPT})
    answer = post_json(
        where,
        "/chat/completions",
        {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
            "top_p": TOP_P,
            "seed": SEED,
            "chat_template_kwargs": {"enable_thinking": False},
        },
    )
    choice = answer["choices"][0]
    if choice.get("finish_reason") == "length":
        raise Incomplete("it did not finish the page (it repeated itself)")
    raw = str(choice["message"].get("content") or "")
    return to_markdown(raw) if grounding else raw.strip()


# ---------------------------------------------------------------------------
# Many pages, with RapidOCR standing in
# ---------------------------------------------------------------------------


class Reader:
    """Reads pictures with LightOnOCR; RapidOCR reads what it cannot.

    ``reader(picture, page)`` returns an :class:`~._ocr.OcrText`. A page LightOn
    fails on (no answer, an error, unfinished) is read by *fallback* when
    there is one; without one the error is raised. Once the endpoint has
    been unreachable, later pages go straight to *fallback* instead of
    waiting for it again. Thread-safe: :func:`~._ocr.read_pages` calls it
    from several threads.
    """

    def __init__(
        self,
        where: Endpoint,
        fallback: Callable[[Any], Any] | None,
        *,
        model: str | None = None,
    ):
        self.where = where
        self.fallback = fallback
        self.model = model or model_name()
        self.unreachable: str | None = None
        self.fell_back: dict[Any, str] = {}  # page (or call number) -> reason
        self._lock = threading.Lock()
        self._calls = 0

    def __call__(self, image: Any, key: Any = None) -> Any:
        """*image* read; *key* (a page number) names it in :attr:`fell_back`."""
        from ._ocr import OcrText

        with self._lock:
            self._calls += 1
            call = self._calls if key is None else key
            down = self.unreachable
        if down is None:
            try:
                return OcrText(read(image, self.where, self.model))
            except Unavailable as e:
                reason = str(e)
                with self._lock:
                    self.unreachable = self.unreachable or reason
            except Incomplete as e:
                reason = str(e)
            except RuntimeError as e:
                reason = str(e)
            except Exception as e:  # noqa: BLE001 - any failure: next engine
                log.warning("LightOn OCR failed: %s: %s", type(e).__name__, e)
                reason = "it failed on the page"
        else:
            reason = down
        if self.fallback is None:
            raise RuntimeError(f"LightOn OCR failed: {reason}")
        log.info("LightOn OCR: %s; RapidOCR reads this page", reason)
        with self._lock:
            self.fell_back[call] = reason
        return self.fallback(image)

    def warning(self, pages: int | None = None) -> str | None:
        """One sentence for ``meta.warnings`` when RapidOCR read anything.

        *pages*: how many pages OCR read (a document); ``None``: an image.
        """
        if not self.fell_back:
            return None
        reasons = "; ".join(sorted(set(self.fell_back.values())))[:300]
        count = len(self.fell_back)
        what = f"{count} of the {pages} scanned pages" if pages else "the image"
        return (
            f"ocr: LightOnOCR did not read {what}: {reasons}. RapidOCR, a "
            f"simpler engine, read {'it' if count == 1 else 'them'} instead"
        )
