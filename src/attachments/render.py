"""Last-mile consumers of artifact lists (VISION Epic A4).

``att()`` returns ``list[Artifact]`` (plain dicts — see
``spec/IR-CONTRACT.md``). This module turns that list into things you can
hand to an LLM right away:

* :func:`render_text` — assemble one prompt string with ``## <source>``
  headers.
* :func:`to_claude_content` / :func:`to_claude_messages` — Claude Messages
  API content blocks / messages (plain JSON-able dicts, no ``anthropic``
  SDK import).
* :func:`to_openai_messages` — OpenAI Chat Completions messages with
  ``image_url`` data-URL parts (plain dicts, no ``openai`` SDK import).
* :func:`chunk` — deterministic, segment-aware chunking for RAG pipelines.

Everything here accepts plain dicts shaped like :class:`attachments.types.
Artifact`, imports nothing heavy, and has zero third-party dependencies.

Example::

    from attachments import att
    from attachments.render import to_claude_messages

    artifacts = att("report.pdf")
    messages = to_claude_messages(artifacts, prompt="Summarize this.")
"""

from __future__ import annotations

import base64
from typing import Any

__all__ = [
    "render_text",
    "to_claude_content",
    "to_claude_messages",
    "to_openai_messages",
    "chunk",
]

#: Header fallback when an artifact has no ``meta.source``.
_UNKNOWN_SOURCE = "(unknown)"

#: Fallback media type when an image item carries no ``mimetype``.
_DEFAULT_MEDIA_TYPE = "application/octet-stream"


def _source(artifact: dict) -> str:
    """Return ``meta.source`` for *artifact*, or a stable placeholder.

    Examples:
        >>> _source({"meta": {"source": "a.txt"}})
        'a.txt'
        >>> _source({})
        '(unknown)'
    """
    meta = artifact.get("meta") or {}
    return meta.get("source") or _UNKNOWN_SOURCE


def _image_b64(image: dict) -> str | None:
    """Return the standard-base64 payload for an image item, or ``None``.

    In-process artifacts carry raw ``bytes``; wire-form artifacts (JSON
    transport, see the IR contract) carry ``bytes_b64`` instead. Both
    work; items with neither are skipped by callers.

    Examples:
        >>> _image_b64({"bytes": b"hi"})
        'aGk='
        >>> _image_b64({"bytes_b64": "aGk="})
        'aGk='
        >>> _image_b64({"name": "broken.png"}) is None
        True
    """
    raw = image.get("bytes")
    if isinstance(raw, bytes | bytearray):
        return base64.b64encode(bytes(raw)).decode("ascii")
    b64 = image.get("bytes_b64")
    if isinstance(b64, str) and b64:
        return b64
    return None


def _iter_images(artifacts: list[dict]) -> list[tuple[str, str]]:
    """Collect ``(media_type, base64_data)`` for every encodable image."""
    out: list[tuple[str, str]] = []
    for artifact in artifacts:
        for image in artifact.get("images") or []:
            data = _image_b64(image)
            if data is None:
                continue
            out.append((image.get("mimetype") or _DEFAULT_MEDIA_TYPE, data))
    return out


# ---------------------------------------------------------------------------
# Prompt string assembly
# ---------------------------------------------------------------------------


def render_text(artifacts: list[dict], *, include_sources: bool = True) -> str:
    """Assemble artifacts into one prompt-ready string.

    For each artifact with non-empty text, emits a ``## <meta.source>``
    header line (when *include_sources*) followed by the text (outer
    whitespace stripped). Artifacts with neither text nor images are
    skipped. Image-only artifacts are noted as ``[image: <name>]`` lines
    under their header so they are not silently lost. Artifacts are
    separated by one blank line.

    Args:
        artifacts: List of artifact dicts (see ``spec/IR-CONTRACT.md``).
        include_sources: Emit ``## <source>`` header lines (default True).

    Returns:
        The assembled string (``""`` for an empty / all-empty list).

    Examples:
        >>> from attachments.types import make_artifact
        >>> notes = make_artifact(text="Alpha beta.", meta={"source": "notes.txt"})
        >>> scan = make_artifact(
        ...     images=[{"name": "scan-1.png", "mimetype": "image/png", "bytes": b""}],
        ...     meta={"source": "scan.pdf"},
        ... )
        >>> print(render_text([notes, scan]))
        ## notes.txt
        Alpha beta.
        <BLANKLINE>
        ## scan.pdf
        [image: scan-1.png]
        >>> render_text([notes], include_sources=False)
        'Alpha beta.'
        >>> render_text([make_artifact()])
        ''
        >>> render_text([])
        ''
    """
    blocks: list[str] = []
    for artifact in artifacts:
        text = (artifact.get("text") or "").strip()
        if text:
            lines = [text]
        else:
            images = artifact.get("images") or []
            if not images:
                continue
            lines = [f"[image: {img.get('name') or 'image'}]" for img in images]
        if include_sources:
            lines.insert(0, f"## {_source(artifact)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Claude Messages API (plain dicts — no anthropic SDK import)
# ---------------------------------------------------------------------------


def to_claude_content(
    artifacts: list[dict], *, prompt: str | None = None
) -> list[dict[str, Any]]:
    """Convert artifacts to Claude Messages API content blocks.

    Produces plain JSON-able dicts matching the Claude wire format: all
    text first as ONE ``{"type": "text", ...}`` block (built with
    :func:`render_text`), then one ``{"type": "image", ...}`` block per
    image (standard base64), then *prompt* appended LAST as a text block
    when given. Images in wire form (``bytes_b64`` instead of ``bytes``)
    are supported.

    Args:
        artifacts: List of artifact dicts.
        prompt: Optional user instruction appended as the final text block.

    Returns:
        Content blocks suitable for ``{"role": "user", "content": ...}``.

    Examples:
        >>> from attachments.types import make_artifact
        >>> art = make_artifact(text="hello", meta={"source": "a.txt"})
        >>> blocks = to_claude_content([art], prompt="Summarize.")
        >>> [b["type"] for b in blocks]
        ['text', 'text']
        >>> blocks[0]["text"]
        '## a.txt\\nhello'
        >>> blocks[-1]
        {'type': 'text', 'text': 'Summarize.'}

        Images become base64 blocks (block 0 is the ``[image: ...]`` note):

        >>> img = {"name": "p.png", "mimetype": "image/png", "bytes": b"\\x89PNG"}
        >>> art = make_artifact(images=[img], meta={"source": "p.pdf"})
        >>> block = to_claude_content([art])[1]
        >>> block["source"]["media_type"]
        'image/png'
        >>> import base64
        >>> base64.b64decode(block["source"]["data"])
        b'\\x89PNG'
        >>> to_claude_content([])
        []
    """
    blocks: list[dict[str, Any]] = []
    text = render_text(artifacts)
    if text:
        blocks.append({"type": "text", "text": text})
    for media_type, data in _iter_images(artifacts):
        blocks.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": data,
                },
            }
        )
    if prompt is not None:
        blocks.append({"type": "text", "text": prompt})
    return blocks


def to_claude_messages(artifacts: list[dict], *, prompt: str) -> list[dict[str, Any]]:
    """Convert artifacts to a complete Claude Messages API ``messages`` list.

    A single user message whose content is :func:`to_claude_content`.
    Plain dicts — pass straight to ``messages=`` in an HTTP request body.

    Examples:
        >>> from attachments.types import make_artifact
        >>> art = make_artifact(text="hi", meta={"source": "a.txt"})
        >>> msgs = to_claude_messages([art], prompt="Go")
        >>> msgs[0]["role"]
        'user'
        >>> [b["type"] for b in msgs[0]["content"]]
        ['text', 'text']
    """
    return [{"role": "user", "content": to_claude_content(artifacts, prompt=prompt)}]


# ---------------------------------------------------------------------------
# OpenAI Chat Completions API (plain dicts — no openai SDK import)
# ---------------------------------------------------------------------------


def to_openai_messages(artifacts: list[dict], *, prompt: str) -> list[dict[str, Any]]:
    """Convert artifacts to OpenAI Chat Completions ``messages``.

    A single user message with multimodal content parts: all text first as
    one ``{"type": "text", ...}`` part (built with :func:`render_text`),
    then one ``{"type": "image_url", ...}`` part per image using a
    ``data:<mimetype>;base64,<b64>`` URL, then *prompt* appended last as a
    text part. Wire-form images (``bytes_b64``) are supported.

    Examples:
        >>> from attachments.types import make_artifact
        >>> img = {"name": "p.png", "mimetype": "image/png", "bytes": b"\\x89PNG"}
        >>> art = make_artifact(text="hi", images=[img], meta={"source": "a.pdf"})
        >>> msgs = to_openai_messages([art], prompt="Go")
        >>> msgs[0]["role"]
        'user'
        >>> [p["type"] for p in msgs[0]["content"]]
        ['text', 'image_url', 'text']
        >>> msgs[0]["content"][1]["image_url"]["url"][:22]
        'data:image/png;base64,'
        >>> msgs[0]["content"][-1]
        {'type': 'text', 'text': 'Go'}
    """
    parts: list[dict[str, Any]] = []
    text = render_text(artifacts)
    if text:
        parts.append({"type": "text", "text": text})
    for media_type, data in _iter_images(artifacts):
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{data}"},
            }
        )
    if prompt is not None:
        parts.append({"type": "text", "text": prompt})
    return [{"role": "user", "content": parts}]


# ---------------------------------------------------------------------------
# Chunking (segment-aware, deterministic)
# ---------------------------------------------------------------------------


def _find_cut(text: str, lo: int, hi: int) -> int | None:
    """Find the best cut point in ``text[lo:hi]``, or ``None``.

    Prefers a paragraph break (``\\n\\n``), then a newline, then a space —
    always the rightmost occurrence. The returned offset points just
    AFTER the separator (the separator stays with the earlier chunk).

    Examples:
        >>> _find_cut("aaa\\n\\nbbb ccc", 0, 11)
        5
        >>> _find_cut("aaa bbb ccc", 0, 11)
        8
        >>> _find_cut("aaaaaa", 0, 6) is None
        True
    """
    for sep in ("\n\n", "\n", " "):
        idx = text.rfind(sep, lo, hi)
        if idx != -1:
            return idx + len(sep)
    return None


def _split_window(text: str, max_chars: int, overlap: int) -> list[str]:
    """Split *text* into windows of at most *max_chars* with *overlap*.

    Each next window starts ``overlap`` characters before the previous
    window's end (clamped to always make progress). When a window does
    not end the text, the split prefers a paragraph / newline / space
    boundary within the last 20% of the window (see :func:`_find_cut`);
    otherwise it cuts hard at *max_chars*. Deterministic; no characters
    are dropped: with no boundary cuts, dropping the first ``overlap``
    chars of every window after the first reconstructs *text* exactly.

    Examples:
        >>> _split_window("abcdefghij", 10, 2)
        ['abcdefghij']
        >>> _split_window("abcdefghijk", 10, 2)
        ['abcdefghij', 'ijk']
        >>> _split_window("", 10, 2)
        []
    """
    if len(text) <= max_chars:
        return [text] if text else []
    pieces: list[str] = []
    n = len(text)
    start = 0
    while True:
        end = min(start + max_chars, n)
        if end < n:
            search_lo = max(start, end - max(1, max_chars // 5))
            cut = _find_cut(text, search_lo, end)
            if cut is not None and cut > start:
                end = cut
        pieces.append(text[start:end])
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return pieces


def _clamped_segments(text: str, segments: list[dict]) -> list[tuple[int, int]]:
    """Return ``(start, end)`` spans for valid, non-empty segments, sorted."""
    spans: list[tuple[int, int]] = []
    n = len(text)
    for seg in segments:
        try:
            start = int(seg.get("start", 0))
            end = int(seg.get("end", 0))
        except (TypeError, ValueError):
            continue
        start = max(0, min(n, start))
        end = max(start, min(n, end))
        if end > start:
            spans.append((start, end))
    return sorted(spans)


def _pack_segments(
    text: str, segments: list[dict], max_chars: int, overlap: int
) -> list[str]:
    """Greedily pack whole segments into chunk bodies of <= *max_chars*.

    Consecutive segments are merged by slicing the original text from the
    first segment's start to the last one's end (preserving whatever
    separates them), as long as the slice fits in *max_chars*. A single
    segment larger than *max_chars* falls back to :func:`_split_window`.

    Examples:
        >>> text = "one\\n\\ntwo\\n\\nthree"
        >>> segs = [
        ...     {"kind": "page", "label": "page 1", "start": 0, "end": 3},
        ...     {"kind": "page", "label": "page 2", "start": 5, "end": 8},
        ...     {"kind": "page", "label": "page 3", "start": 10, "end": 15},
        ... ]
        >>> _pack_segments(text, segs, 8, 0)
        ['one\\n\\ntwo', 'three']
        >>> _pack_segments(text, segs, 100, 0)
        ['one\\n\\ntwo\\n\\nthree']
    """
    spans = _clamped_segments(text, segments)
    bodies: list[str] = []
    i = 0
    while i < len(spans):
        start, end = spans[i]
        if end - start > max_chars:
            bodies.extend(_split_window(text[start:end], max_chars, overlap))
            i += 1
            continue
        j = i + 1
        while j < len(spans) and max(end, spans[j][1]) - start <= max_chars:
            end = max(end, spans[j][1])
            j += 1
        bodies.append(text[start:end])
        i = j
    return bodies


def chunk(
    artifacts: list[dict], *, max_chars: int = 8000, overlap: int = 200
) -> list[str]:
    """Split artifacts into prompt-sized chunks, respecting structure.

    For each artifact with non-empty text:

    * If ``meta.segments`` is present (pages/sheets/slides — see the IR
      contract), whole segments are packed greedily into chunks of at
      most *max_chars* characters; segments are never split unless a
      single segment alone exceeds *max_chars*, in which case that
      segment falls back to character-window splitting with *overlap*.
    * Otherwise the text is window-split: windows of at most *max_chars*
      that prefer to break at a paragraph (``\\n\\n``), then newline, then
      space boundary within the last 20% of the window, with *overlap*
      characters repeated at the start of each following window.

    Every chunk is prefixed with a ``## <source>`` header line (the
    header does not count against *max_chars*). Empty artifacts
    contribute nothing; an empty list returns ``[]``. Output is fully
    deterministic.

    Args:
        artifacts: List of artifact dicts.
        max_chars: Maximum characters per chunk body (must be >= 1).
        overlap: Characters repeated between consecutive window chunks
            (clamped to ``[0, max_chars - 1]``).

    Returns:
        List of chunk strings, in artifact order.

    Raises:
        ValueError: If ``max_chars < 1``.

    Examples:
        >>> from attachments.types import make_artifact
        >>> art = make_artifact(text="alpha beta gamma", meta={"source": "a.txt"})
        >>> chunk([art])
        ['## a.txt\\nalpha beta gamma']
        >>> chunk([art], max_chars=12, overlap=0)
        ['## a.txt\\nalpha beta ', '## a.txt\\ngamma']
        >>> chunk([make_artifact()])
        []
        >>> chunk([])
        []
    """
    if max_chars < 1:
        raise ValueError(f"max_chars must be >= 1, got {max_chars}")
    overlap = max(0, min(int(overlap), max_chars - 1))

    chunks: list[str] = []
    for artifact in artifacts:
        text = artifact.get("text") or ""
        if not text.strip():
            continue
        meta = artifact.get("meta") or {}
        segments = meta.get("segments") or []
        if segments:
            bodies = _pack_segments(text, segments, max_chars, overlap)
        else:
            bodies = _split_window(text, max_chars, overlap)
        header = f"## {_source(artifact)}"
        chunks.extend(f"{header}\n{body}" for body in bodies)
    return chunks
