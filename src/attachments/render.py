"""Last-mile consumers of artifact lists (VISION Epic A4).

``att()`` returns ``list[Artifact]`` (plain dicts — see
``spec/IR-CONTRACT.md``). This module turns that list into things you can
hand to an LLM right away:

* :func:`render_text` — assemble one prompt string with ``## <source>``
  headers.
* :func:`to_parts` — the provider-neutral content list (text and image
  parts, each page's text followed by that page's images). Every
  presenter below is built from it.
* :func:`to_claude_content` / :func:`to_claude_messages` — Claude Messages
  API content blocks / messages (plain JSON-able dicts, no ``anthropic``
  SDK import).
* :func:`to_openai_messages` — OpenAI Chat Completions messages with
  ``image_url`` data-URL parts (plain dicts, no ``openai`` SDK import).
* :func:`chunk` — deterministic, segment-aware chunking for RAG pipelines.
* :func:`estimate_tokens` — a rough token count, text and images.

Every function takes ``sources=`` (default ``True``): whether file names
(``## <source>`` headers, ``[image: <name>]`` notes) reach the output.
Turn it off when the names would tell the model the answer (a photo
called ``tabby_cat.png`` in a "which animal?" task). Folder overviews
(``meta.kind == "directory"``) are made of names, so ``sources=False``
leaves them out entirely.

Everything here accepts plain dicts shaped like :class:`attachments.types.
Artifact`, in-process (``bytes``) or wire form (``bytes_b64``), imports
nothing heavy, and has zero third-party dependencies.

Example::

    from attachments import att
    from attachments.render import to_claude_messages

    artifacts = att("report.pdf")
    messages = to_claude_messages(artifacts, prompt="Summarize this.")
"""

from __future__ import annotations

import base64
import binascii
from typing import Any

from ._imagesize import image_size
from ._limits import CLAUDE, OPENAI, check_request

__all__ = [
    "render_text",
    "to_parts",
    "to_claude_content",
    "to_claude_messages",
    "to_openai_messages",
    "chunk",
    "estimate_tokens",
    "image_tokens",
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


def _image_part(image: dict) -> dict[str, Any] | None:
    """The neutral image part for *image*, or ``None`` when it has no data."""
    data = _image_b64(image)
    if data is None:
        return None
    return {
        "type": "image",
        "media_type": image.get("mimetype") or _DEFAULT_MEDIA_TYPE,
        "data": data,
    }


# ---------------------------------------------------------------------------
# Prompt string assembly
# ---------------------------------------------------------------------------


def _shown(artifacts: list[dict], sources: bool) -> list[dict]:
    """The artifacts to present: without file names, no folder overviews.

    Examples:
        >>> tree = {"text": "docs/\\n└── cat.jpg", "meta": {"kind": "directory"}}
        >>> photo = {"text": "", "images": [], "meta": {}}
        >>> len(_shown([tree, photo], True)), len(_shown([tree, photo], False))
        (2, 1)
    """
    if sources:
        return list(artifacts)
    return [a for a in artifacts if (a.get("meta") or {}).get("kind") != "directory"]


def render_text(artifacts: list[dict], *, sources: bool = True) -> str:
    """Assemble artifacts into one prompt-ready string.

    For each artifact with non-empty text, emits a ``## <meta.source>``
    header line (when *sources*) followed by the text (outer whitespace
    stripped). Artifacts are separated by one blank line; artifacts with
    nothing to show are skipped.

    An artifact with images but no text is noted as one ``[image: <name>]``
    line per image under its header, so it is not silently lost from a
    text-only view. With ``sources=False`` the note keeps no name:
    ``[image]``.

    Args:
        artifacts: List of artifact dicts (see ``spec/IR-CONTRACT.md``).
        sources: Show file names — ``## <source>`` headers and the names
            in ``[image: <name>]`` notes (default True).

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
        >>> render_text([notes, scan], sources=False)
        'Alpha beta.\\n\\n[image]'
        >>> render_text([make_artifact()])
        ''
        >>> render_text([])
        ''
    """
    blocks: list[str] = []
    for artifact in _shown(artifacts, sources):
        text = (artifact.get("text") or "").strip()
        if text:
            lines = [text]
        elif artifact.get("images"):
            lines = [
                f"[image: {img.get('name') or 'image'}]" if sources else "[image]"
                for img in artifact["images"]
            ]
        else:
            continue
        if sources:
            lines.insert(0, f"## {_source(artifact)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Provider-neutral parts (the one source of truth for every presenter)
# ---------------------------------------------------------------------------


def _paged_segments(artifact: dict) -> list[tuple[int, int, int]]:
    """``(start, end, page)`` for segments that carry a page number."""
    meta = artifact.get("meta") or {}
    out: list[tuple[int, int, int]] = []
    for seg in meta.get("segments") or []:
        page, start, end = seg.get("page"), seg.get("start"), seg.get("end")
        if all(
            isinstance(v, int) and not isinstance(v, bool) for v in (page, start, end)
        ):
            out.append((start, end, page))
    return sorted(out)


def _image_page(image: dict) -> int | None:
    page = image.get("page")
    return page if isinstance(page, int) and not isinstance(page, bool) else None


def _artifact_pieces(artifact: dict, *, interleave: bool) -> list[dict[str, Any]]:
    """Text and image parts of ONE artifact, without any file name.

    With *interleave*, and when both the text segments and the images
    carry page numbers (``Segment.page`` / ``ImageItem.page``), the text
    is cut only where an image goes: after the text of its page. Text
    between two cuts stays one part, with its original separators. Images
    of a page that has no segment go before the first later page; images
    with no page, or past the last page, go at the end. Otherwise: the
    whole text, then every image.

    Examples:
        >>> art = {
        ...     "text": "one\\n\\ntwo\\n\\nthree",
        ...     "images": [
        ...         {"name": "p1", "mimetype": "image/png", "bytes": b"1", "page": 1},
        ...         {"name": "p3", "mimetype": "image/png", "bytes": b"3", "page": 3},
        ...     ],
        ...     "meta": {
        ...         "segments": [
        ...             {
        ...                 "kind": "page",
        ...                 "label": "page 1",
        ...                 "start": 0,
        ...                 "end": 3,
        ...                 "page": 1,
        ...             },
        ...             {
        ...                 "kind": "page",
        ...                 "label": "page 2",
        ...                 "start": 5,
        ...                 "end": 8,
        ...                 "page": 2,
        ...             },
        ...             {
        ...                 "kind": "page",
        ...                 "label": "page 3",
        ...                 "start": 10,
        ...                 "end": 15,
        ...                 "page": 3,
        ...             },
        ...         ]
        ...     },
        ... }
        >>> [p.get("text", p["type"]) for p in _artifact_pieces(art, interleave=True)]
        ['one', 'image', 'two\\n\\nthree', 'image']
        >>> [p.get("text", p["type"]) for p in _artifact_pieces(art, interleave=False)]
        ['one\\n\\ntwo\\n\\nthree', 'image', 'image']
    """
    text = artifact.get("text") or ""
    images = [
        (image, part)
        for image in artifact.get("images") or []
        if (part := _image_part(image)) is not None
    ]
    pieces: list[dict[str, Any]] = []
    cursor = 0

    def flush(upto: int) -> None:
        nonlocal cursor
        if upto > cursor:
            piece = text[cursor:upto].strip()
            if piece:
                pieces.append({"type": "text", "text": piece})
            cursor = upto

    segments = _paged_segments(artifact) if interleave else []
    if segments and any(_image_page(image) is not None for image, _ in images):
        pending = list(images)

        def take(predicate) -> list[dict[str, Any]]:
            nonlocal pending
            taken = [part for image, part in pending if predicate(_image_page(image))]
            pending = [(i, p) for i, p in pending if not predicate(_image_page(i))]
            return taken

        for start, end, page in segments:
            before = take(lambda p, page=page: p is not None and p < page)
            if before:
                flush(start)
                pieces.extend(before)
            here = take(lambda p, page=page: p == page)
            if here:
                flush(end)
                pieces.extend(here)
        images = pending
    flush(len(text))
    pieces.extend(part for _, part in images)
    return pieces


def to_parts(
    artifacts: list[dict],
    *,
    sources: bool = True,
    interleave: bool = True,
    prompt: str | None = None,
) -> list[dict[str, Any]]:
    """Convert artifacts to a provider-neutral list of content parts.

    Two part shapes, plain JSON-able dicts::

        {"type": "text", "text": "..."}
        {"type": "image", "media_type": "image/png", "data": "<base64>"}

    Each artifact contributes its text and its images. With *interleave*
    (default), a page's text is followed by that page's images, so the
    model never has to match page 7's picture to page 7's words by
    itself. This needs page numbers on both sides (``Segment.page`` and
    ``ImageItem.page``, set by the pdf and pptx processors); without them,
    an artifact gives its text, then its images. With ``interleave=False``
    the whole list is one text part (:func:`render_text`) followed by
    every image.

    Neighbouring text parts are merged (blank line between them), so a
    text-only input gives exactly one text part equal to
    :func:`render_text`. *prompt*, when given, is appended as its own
    last text part.

    Args:
        artifacts: List of artifact dicts (in-process or wire form).
        sources: Show file names: each artifact's text starts with
            ``## <source>`` (default True). With ``False`` no name reaches
            the parts at all.
        interleave: Put each page's images right after its text (default
            True).
        prompt: Optional instruction appended as the final text part.

    Examples:
        >>> from attachments.types import make_artifact
        >>> img = {"name": "cat.png", "mimetype": "image/png", "bytes": b"\\x89PNG"}
        >>> photo = make_artifact(images=[img], meta={"source": "cat.png"})
        >>> [p.get("text", p["type"]) for p in to_parts([photo], prompt="Animal?")]
        ['## cat.png', 'image', 'Animal?']
        >>> [p.get("text", p["type"]) for p in to_parts([photo], sources=False)]
        ['image']
        >>> to_parts([make_artifact(text="hi", meta={"source": "a.txt"})])
        [{'type': 'text', 'text': '## a.txt\\nhi'}]
        >>> to_parts([])
        []
    """
    parts: list[dict[str, Any]] = []

    def add(part: dict[str, Any]) -> None:
        if part["type"] == "text" and parts and parts[-1]["type"] == "text":
            parts[-1] = {
                "type": "text",
                "text": f"{parts[-1]['text']}\n\n{part['text']}",
            }
        else:
            parts.append(part)

    artifacts = _shown(artifacts, sources)
    if interleave:
        for artifact in artifacts:
            pieces = _artifact_pieces(artifact, interleave=True)
            if not pieces:
                continue
            if sources:
                header = f"## {_source(artifact)}"
                if pieces[0]["type"] == "text":
                    pieces[0] = {
                        "type": "text",
                        "text": f"{header}\n{pieces[0]['text']}",
                    }
                else:
                    pieces.insert(0, {"type": "text", "text": header})
            for piece in pieces:
                add(piece)
    else:
        text = render_text(artifacts, sources=sources)
        if text:
            add({"type": "text", "text": text})
        for artifact in artifacts:
            for image in artifact.get("images") or []:
                part = _image_part(image)
                if part is not None:
                    parts.append(part)

    if prompt:
        parts.append({"type": "text", "text": prompt})
    return parts


# ---------------------------------------------------------------------------
# Claude Messages API (plain dicts — no anthropic SDK import)
# ---------------------------------------------------------------------------


def to_claude_content(
    artifacts: list[dict],
    *,
    prompt: str | None = None,
    sources: bool = True,
    interleave: bool = True,
) -> list[dict[str, Any]]:
    """Convert artifacts to Claude Messages API content blocks.

    :func:`to_parts` in Claude's wire format: text parts become
    ``{"type": "text", ...}`` blocks and image parts become
    ``{"type": "image", "source": {"type": "base64", ...}}`` blocks, in
    the same order (each page's text, then its images), with *prompt* as
    the last text block when given. Wire-form images (``bytes_b64``) work.

    A request that breaks a published Claude limit (32 MB, picture count,
    size and dimensions, formats) gives a :class:`~attachments.
    RequestLimitWarning` that names the problem and the fix.

    Args:
        artifacts: List of artifact dicts.
        prompt: Optional user instruction appended as the final text block.
        sources: Show file names (see :func:`to_parts`).
        interleave: Each page's images right after its text (see
            :func:`to_parts`).

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

        Images become base64 blocks:

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
    parts = to_parts(artifacts, sources=sources, interleave=interleave, prompt=prompt)
    check_request(parts, CLAUDE)
    blocks: list[dict[str, Any]] = []
    for part in parts:
        if part["type"] == "text":
            blocks.append({"type": "text", "text": part["text"]})
        else:
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": part["media_type"],
                        "data": part["data"],
                    },
                }
            )
    return blocks


def to_claude_messages(
    artifacts: list[dict],
    *,
    prompt: str | None = None,
    sources: bool = True,
    interleave: bool = True,
) -> list[dict[str, Any]]:
    """Convert artifacts to a complete Claude Messages API ``messages`` list.

    A single user message whose content is :func:`to_claude_content`.
    Plain dicts — pass straight to ``messages=`` in an HTTP request body.
    *prompt* is optional: when omitted (or empty), no trailing prompt
    text block is appended.

    Examples:
        >>> from attachments.types import make_artifact
        >>> art = make_artifact(text="hi", meta={"source": "a.txt"})
        >>> msgs = to_claude_messages([art], prompt="Go")
        >>> msgs[0]["role"]
        'user'
        >>> [b["type"] for b in msgs[0]["content"]]
        ['text', 'text']
        >>> [b["type"] for b in to_claude_messages([art])[0]["content"]]
        ['text']
    """
    content = to_claude_content(
        artifacts, prompt=prompt, sources=sources, interleave=interleave
    )
    return [{"role": "user", "content": content}]


# ---------------------------------------------------------------------------
# OpenAI Chat Completions API (plain dicts — no openai SDK import)
# ---------------------------------------------------------------------------


def to_openai_messages(
    artifacts: list[dict],
    *,
    prompt: str | None = None,
    sources: bool = True,
    interleave: bool = True,
) -> list[dict[str, Any]]:
    """Convert artifacts to OpenAI Chat Completions ``messages``.

    A single user message whose content is :func:`to_parts` in OpenAI's
    format: text parts stay ``{"type": "text", ...}`` and image parts
    become ``{"type": "image_url", ...}`` with a
    ``data:<mimetype>;base64,<b64>`` URL, in the same order, with
    *prompt* as the last text part when given. Wire-form images
    (``bytes_b64``) are supported. A request over a published OpenAI limit
    gives a :class:`~attachments.RequestLimitWarning`.

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
        >>> [p["type"] for p in to_openai_messages([art])[0]["content"]]
        ['text', 'image_url']
    """
    parts = to_parts(artifacts, sources=sources, interleave=interleave, prompt=prompt)
    check_request(parts, OPENAI)
    content: list[dict[str, Any]] = []
    for part in parts:
        if part["type"] == "text":
            content.append({"type": "text", "text": part["text"]})
        else:
            url = f"data:{part['media_type']};base64,{part['data']}"
            content.append({"type": "image_url", "image_url": {"url": url}})
    return [{"role": "user", "content": content}]


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


#: Default chunk-body size (characters) when neither cap is given.
_DEFAULT_MAX_CHARS = 8000

#: Characters assumed per token by the ``max_tokens`` approximation.
_CHARS_PER_TOKEN = 4


def chunk(
    artifacts: list[dict],
    *,
    max_chars: int | None = None,
    max_tokens: int | None = None,
    overlap: int = 200,
    sources: bool = True,
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
    header does not count against *max_chars*) unless ``sources=False``. Empty artifacts
    contribute nothing; an empty list returns ``[]``. Output is fully
    deterministic.

    Token budgets: *max_tokens* expresses the cap in approximate tokens
    using the fast 4-characters-per-token heuristic (NOT a real
    tokenizer): ``chunk(a, max_tokens=N)`` is exactly
    ``chunk(a, max_chars=N * 4)``. When BOTH *max_chars* and *max_tokens*
    are given, the smaller character budget wins. When neither is given,
    the default is 8000 characters.

    Args:
        artifacts: List of artifact dicts.
        max_chars: Maximum characters per chunk body (must be >= 1).
            Default 8000 when *max_tokens* is also omitted.
        max_tokens: Approximate-token cap; converted to a character cap
            via ``max_tokens * 4`` (must be >= 1). Overrides the default
            *max_chars*; with both given, the smaller cap wins.
        overlap: Characters repeated between consecutive window chunks
            (clamped to ``[0, max_chars - 1]``).
        sources: Prefix each chunk with its ``## <source>`` header
            (default True).

    Returns:
        List of chunk strings, in artifact order.

    Raises:
        ValueError: If the effective character cap is < 1.

    Examples:
        >>> from attachments.types import make_artifact
        >>> art = make_artifact(text="alpha beta gamma", meta={"source": "a.txt"})
        >>> chunk([art])
        ['## a.txt\\nalpha beta gamma']
        >>> chunk([art], max_chars=12, overlap=0)
        ['## a.txt\\nalpha beta ', '## a.txt\\ngamma']
        >>> chunk([art], max_tokens=3, overlap=0)  # == max_chars=12
        ['## a.txt\\nalpha beta ', '## a.txt\\ngamma']
        >>> chunk([art], max_chars=12, max_tokens=1000, overlap=0)  # smaller wins
        ['## a.txt\\nalpha beta ', '## a.txt\\ngamma']
        >>> chunk([art], max_chars=12, overlap=0, sources=False)
        ['alpha beta ', 'gamma']
        >>> chunk([make_artifact()])
        []
        >>> chunk([])
        []
    """
    caps = []
    if max_chars is not None:
        caps.append(max_chars)
    if max_tokens is not None:
        caps.append(max_tokens * _CHARS_PER_TOKEN)
    max_chars = min(caps) if caps else _DEFAULT_MAX_CHARS
    if max_chars < 1:
        raise ValueError(f"max_chars must be >= 1, got {max_chars}")
    overlap = max(0, min(int(overlap), max_chars - 1))

    chunks: list[str] = []
    for artifact in _shown(artifacts, sources):
        text = artifact.get("text") or ""
        if not text.strip():
            continue
        meta = artifact.get("meta") or {}
        segments = meta.get("segments") or []
        if segments:
            bodies = _pack_segments(text, segments, max_chars, overlap)
        else:
            bodies = _split_window(text, max_chars, overlap)
        if sources:
            header = f"## {_source(artifact)}"
            chunks.extend(f"{header}\n{body}" for body in bodies)
        else:
            chunks.extend(bodies)
    return chunks


# ---------------------------------------------------------------------------
# Token estimate (text and images)
# ---------------------------------------------------------------------------

#: Longest image side a model sees; larger images are shrunk first
#: (Anthropic's published rule for Claude).
_IMAGE_MAX_EDGE = 1568

#: Pixels per image token (Anthropic: tokens ~= width * height / 750).
_PIXELS_PER_TOKEN = 750

#: Most tokens one image costs: Anthropic also shrinks any image over
#: ~1,600 tokens (~1.2 megapixels). Also the charge for an image whose
#: size cannot be read — an upper bound, so budgets stay safe.
_IMAGE_MAX_TOKENS = 1600


def image_tokens(width: int, height: int) -> int:
    """Approximate tokens for one image of *width* x *height* pixels.

    Anthropic's published rule for Claude: shrink so the longest side is
    at most 1,568 pixels and the image is at most ~1,600 tokens, then
    count ``width * height / 750``. Other providers count differently
    (OpenAI's tile rule gives roughly 1,100 for a full page), so treat
    the result as a budget figure, not billing math.

    Examples:
        >>> image_tokens(750, 1)
        1
        >>> image_tokens(1000, 750)
        1000
        >>> image_tokens(2667, 1500)  # a 200 dpi slide-sized page
        1600
        >>> image_tokens(3000, 100)  # long and thin: only the edge rule bites
        110
    """
    if width <= 0 or height <= 0:
        return 0
    scale = min(1.0, _IMAGE_MAX_EDGE / max(width, height))
    pixels = (width * scale) * (height * scale)
    return max(1, min(_IMAGE_MAX_TOKENS, -(-int(pixels) // _PIXELS_PER_TOKEN)))


def _image_item_tokens(image: dict) -> int:
    """Tokens for one ImageItem (in-process or wire form)."""
    raw = image.get("bytes")
    if not isinstance(raw, bytes | bytearray):
        b64 = image.get("bytes_b64")
        if not isinstance(b64, str) or not b64:
            return 0  # no payload: presenters skip it, so it costs nothing
        try:
            raw = base64.b64decode(b64)
        except (binascii.Error, ValueError):
            return 0
    size = image_size(bytes(raw))
    if size is None:
        return _IMAGE_MAX_TOKENS
    return image_tokens(*size)


def estimate_tokens(artifacts: list[dict]) -> dict[str, int]:
    """Rough token cost of *artifacts*: ``{"text", "images", "total"}``.

    Text: characters / 4, rounded up (a fast approximation, not a
    tokenizer). Images: :func:`image_tokens` on each image's size, read
    from its file header (PNG, JPEG, GIF, WebP, BMP); an image whose size
    cannot be read counts as the maximum, ~1,600. File-name headers that
    presenters add are not counted.

    Examples:
        >>> from attachments.types import make_artifact
        >>> png = bytes.fromhex(
        ...     "89504e470d0a1a0a0000000d49484452000003e8000002ee08060000001f15c489"
        ... )  # a 1000 x 750 PNG header
        >>> art = make_artifact(
        ...     text="abcdefgh",
        ...     images=[{"name": "p.png", "mimetype": "image/png", "bytes": png}],
        ... )
        >>> estimate_tokens([art])
        {'text': 2, 'images': 1000, 'total': 1002}
        >>> estimate_tokens([])
        {'text': 0, 'images': 0, 'total': 0}
    """
    chars = sum(len(artifact.get("text") or "") for artifact in artifacts)
    text = -(-chars // _CHARS_PER_TOKEN)
    images = sum(
        _image_item_tokens(image)
        for artifact in artifacts
        for image in artifact.get("images") or []
    )
    return {"text": text, "images": images, "total": text + images}
