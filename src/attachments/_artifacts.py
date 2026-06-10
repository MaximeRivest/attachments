"""The :class:`Artifacts` container returned by ``att()``.

``att()`` returns :class:`Artifacts` — a ``list`` subclass whose elements
remain plain Artifact dicts (see ``spec/IR-CONTRACT.md``). Everything here
is sugar AROUND the frozen IR, never a change to it: iteration, indexing,
``json.dumps``, and every existing consumer of ``list[Artifact]`` keep
working unchanged.

What the sugar buys you in a REPL or notebook::

    a = att("report.pdf")
    a  # one summary line, never dumps text/bytes
    print(a)  # the full assembled prompt text (render_text)
    a.text  # same string, as a property
    a.images  # flattened ImageItem dicts across artifacts
    a.errors  # [{"source", "code", "message"}, ...]
    a.claude("Go")  # Claude Messages API messages
    a.openai("Go")  # OpenAI Chat Completions messages
    a.chunk()  # RAG chunks
    a[0]  # still a plain dict; a[:2] is Artifacts again

Underscore-prefixed module (repo convention): the public re-export is
``attachments.Artifacts``, and public re-exports must not shadow modules.
This module imports from ``.render``; ``.render`` must never import this
module (circular-import care — ``core`` imports ``Artifacts`` from here).
"""

from __future__ import annotations

import base64
import re
from typing import Any

from .render import chunk as _chunk
from .render import render_text, to_claude_messages, to_openai_messages

__all__ = ["Artifacts"]

#: Per-image payload cap for Jupyter thumbnails (1 MiB of decoded bytes).
_THUMBNAIL_MAX_BYTES = 1024 * 1024

#: Maximum number of thumbnails embedded in ``_repr_markdown_``.
_THUMBNAIL_MAX_COUNT = 4

#: Characters of assembled text shown in the ``_repr_markdown_`` preview.
_PREVIEW_CHARS = 600

#: Characters of an error message shown per ``__repr__`` error line.
#: Wide enough for the missing-dependency messages, whose actionable
#: remedy ("Install with: pip install attachments[pdf]") sits at the end.
_ERROR_MESSAGE_CHARS = 160

#: Maximum number of error lines/admonitions shown by the reprs; the rest
#: collapse into one "+N more errors (see .errors)" line so a directory of
#: failures can never scroll the summary off screen.
_ERROR_MAX_COUNT = 10


def _plural(count: int, noun: str) -> str:
    """Format ``count noun(s)`` with naive pluralization.

    Examples:
        >>> _plural(1, "artifact")
        '1 artifact'
        >>> _plural(3, "image")
        '3 images'
        >>> _plural(0, "error")
        '0 errors'
    """
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _clip_message(message: str) -> str:
    """Clip *message* to the per-line cap, keeping the actionable tail.

    Error messages put the remedy at the END (missing-dependency messages
    always end with the ``pip install`` hint — IR contract), so an
    over-long message is truncated in the MIDDLE, with an ellipsis marking
    the cut. Messages at or under the cap pass through untouched.

    Examples:
        >>> _clip_message("short")
        'short'
        >>> remedy = "Install with: pip install attachments[pdf]"
        >>> clipped = _clip_message("x" * 300 + " " + remedy)
        >>> len(clipped) == _ERROR_MESSAGE_CHARS
        True
        >>> clipped.endswith(remedy)
        True
        >>> "…" in clipped
        True
    """
    if len(message) <= _ERROR_MESSAGE_CHARS:
        return message
    head = (_ERROR_MESSAGE_CHARS - 1) // 2
    tail = _ERROR_MESSAGE_CHARS - 1 - head
    return f"{message[:head]}…{message[-tail:]}"


def _collapse_lines(entries: list[tuple[str, str]]) -> list[str]:
    """Collapse repeated rendered content into one line with ``(xN)``.

    *entries* are ``(source, content)`` pairs where *content* is the
    rendered line content AFTER clipping (the dedupe key). First-seen
    order is preserved. A content seen once renders as
    ``"source: content"``; repeated content collapses to ONE line —
    ``"content (xN)"`` — dropping the per-file sources, which is what
    gives repeated errors/notes a once-per-process feel: a directory of
    40 scanned PDFs shows ONE hint line with ``(x40)``, not 10 plus
    overflow.

    Examples:
        >>> _collapse_lines([("a.pdf", "hint"), ("b.txt", "odd"), ("c.pdf", "hint")])
        ['hint (x2)', 'b.txt: odd']
        >>> _collapse_lines([("f.pdf", "only")])
        ['f.pdf: only']
        >>> _collapse_lines([])
        []
    """
    order: dict[str, list[str]] = {}
    for source, content in entries:
        order.setdefault(content, []).append(source)
    return [
        f"{sources[0]}: {content}"
        if len(sources) == 1
        else f"{content} (x{len(sources)})"
        for content, sources in order.items()
    ]


def _format_tokens(n: int) -> str:
    """Compact ``~N tokens`` summary segment for *n* estimated tokens.

    Under 1,000 the exact estimate is shown; thousands and millions get
    one decimal with a trailing ``.0`` stripped.

    Examples:
        >>> _format_tokens(842)
        '~842 tokens'
        >>> _format_tokens(999)
        '~999 tokens'
        >>> _format_tokens(1000)
        '~1k tokens'
        >>> _format_tokens(3553)
        '~3.6k tokens'
        >>> _format_tokens(1_200_000)
        '~1.2M tokens'
        >>> _format_tokens(2_000_000)
        '~2M tokens'
    """
    if n >= 1_000_000:
        value, suffix = n / 1_000_000, "M"
    elif n >= 1000:
        value, suffix = n / 1000, "k"
    else:
        return f"~{n} tokens"
    return f"~{f'{value:.1f}'.removesuffix('.0')}{suffix} tokens"


def _fence(content: str) -> str:
    """Return a backtick fence longer than any backtick run in *content*.

    CommonMark closes a fenced block at the first backtick run at least as
    long as the opener, so a preview containing ``` would terminate a
    plain three-backtick fence early and the rest of the preview would
    render as live markdown (headings, images, a dangling open fence).

    Examples:
        >>> _fence("plain text")
        '```'
        >>> _fence("has ``` inside")
        '````'
        >>> _fence("has ````` inside")
        '``````'
    """
    longest = max((len(m.group()) for m in re.finditer(r"`+", content)), default=0)
    return "`" * max(3, longest + 1)


def _image_payload_b64(image: dict) -> str | None:
    """Return the base64 payload for *image* if it fits the thumbnail cap.

    Handles both in-process images (raw ``bytes``) and wire-form images
    (``bytes_b64`` — see the IR contract). Returns ``None`` when the
    decoded payload exceeds 1 MiB or no payload is present.

    Examples:
        >>> _image_payload_b64({"bytes": b"hi"})
        'aGk='
        >>> _image_payload_b64({"bytes_b64": "aGk="})
        'aGk='
        >>> _image_payload_b64({"bytes": b"x" * (1024 * 1024 + 1)}) is None
        True
        >>> _image_payload_b64({"name": "ghost.png"}) is None
        True
    """
    raw = image.get("bytes")
    if isinstance(raw, bytes | bytearray):
        if len(raw) > _THUMBNAIL_MAX_BYTES:
            return None
        return base64.b64encode(bytes(raw)).decode("ascii")
    b64 = image.get("bytes_b64")
    if isinstance(b64, str) and b64:
        # Decoded size is ~3/4 of the base64 length; close enough for a cap.
        if (len(b64) * 3) // 4 > _THUMBNAIL_MAX_BYTES:
            return None
        return b64
    return None


class Artifacts(list):
    """List of plain Artifact dicts with a delightful interactive surface.

    **v1 muscle memory:** ``print(ctx)`` gives you the assembled prompt
    text. ``str(artifacts)`` (and the ``.text`` property) is exactly
    ``render_text(artifacts)`` — the same ``## <source>``-headed prompt
    string the last mile builds. The ``repr`` (what a bare REPL/notebook
    line shows) is a one-line summary instead, and NEVER dumps text or
    image bytes.

    Elements are plain dicts per ``spec/IR-CONTRACT.md`` — this class adds
    behavior, never state: slicing and concatenation return ``Artifacts``,
    a single index returns the dict as-is, and ``json.dumps`` works
    because ``Artifacts`` *is* a list.

    Examples:
        >>> from attachments.types import error_artifact, make_artifact
        >>> a = Artifacts(
        ...     [
        ...         make_artifact(text="Alpha beta.", meta={"source": "notes.txt"}),
        ...         error_artifact("broken.pdf", "parse-error", "not a PDF"),
        ...     ]
        ... )
        >>> print(repr(a))
        <Artifacts: 2 artifacts | 11 chars | ~3 tokens | 1 error>
          ! broken.pdf: parse-error — not a PDF
        >>> print(a)
        ## notes.txt
        Alpha beta.
        >>> a.errors
        [{'source': 'broken.pdf', 'code': 'parse-error', 'message': 'not a PDF'}]
        >>> isinstance(a[:1], Artifacts)
        True
        >>> isinstance(a[0], dict)
        True
        >>> len(a + a)
        4
    """

    # -- summary lines ------------------------------------------------------

    def _summary(self) -> str:
        """One deterministic summary line (no text/bytes ever).

        ``chars`` counts artifact text characters (summed across
        artifacts, before ``render_text`` adds headers); ``~N tokens``
        is the :attr:`tokens` estimate, compact-formatted.

        Examples:
            >>> from attachments.types import make_artifact
            >>> Artifacts([make_artifact(text="hi")])._summary()
            '1 artifact | 2 chars | ~1 tokens'
        """
        chars = sum(len(artifact.get("text") or "") for artifact in self)
        parts = [
            _plural(len(self), "artifact"),
            f"{chars:,} chars",
            _format_tokens(self.tokens),
        ]
        n_images = len(self.images)
        if n_images:
            parts.append(_plural(n_images, "image"))
        n_errors = len(self.errors)
        if n_errors:
            parts.append(_plural(n_errors, "error"))
        return " | ".join(parts)

    def __repr__(self) -> str:
        """Summary line plus one ``!`` line per error and one ``*`` line per
        note — never text/bytes.

        Identical error content and identical note content (compared AFTER
        clipping) collapse into a single line suffixed ``(xN)`` — a
        once-per-process feel, in first-seen order. UNIQUE lines are capped
        at ``_ERROR_MAX_COUNT``; the rest collapse into one ``+N more
        errors (see .errors)`` line so the repr stays a glance even when a
        whole directory fails. Teaching notes that processors leave in
        ``meta["note"]`` (e.g. the scanned-PDF OCR hint) are surfaced the
        same way, so a first-run user who just prints the result sees the
        guidance — and a directory of 40 scanned PDFs shows ONE hint line
        with ``(x40)``.

        Examples:
            >>> from attachments.types import make_artifact
            >>> Artifacts([make_artifact(text="hello", meta={"source": "a.txt"})])
            <Artifacts: 1 artifact | 5 chars | ~2 tokens>
            >>> Artifacts([make_artifact(meta={"source": "scan.pdf", "note": "hint"})])
            <Artifacts: 1 artifact | 0 chars | ~0 tokens>
              * scan.pdf: hint
            >>> Artifacts(
            ...     [
            ...         make_artifact(meta={"source": f"scan-{i}.pdf", "note": "hint"})
            ...         for i in range(40)
            ...     ]
            ... )
            <Artifacts: 40 artifacts | 0 chars | ~0 tokens>
              * hint (x40)
        """
        lines = [f"<Artifacts: {self._summary()}>"]
        error_lines = _collapse_lines(
            [
                (
                    error["source"],
                    f"{error['code']} — {_clip_message(error['message'])}",
                )
                for error in self.errors
            ]
        )
        lines.extend(f"  ! {line}" for line in error_lines[:_ERROR_MAX_COUNT])
        hidden = len(error_lines) - _ERROR_MAX_COUNT
        if hidden > 0:
            lines.append(f"  … +{_plural(hidden, 'more error')} (see .errors)")
        note_lines = _collapse_lines(
            [
                (artifact["meta"].get("source", "?"), _clip_message(note))
                for artifact in self
                if (note := artifact.get("meta", {}).get("note"))
            ]
        )
        lines.extend(f"  * {line}" for line in note_lines[:_ERROR_MAX_COUNT])
        hidden_notes = len(note_lines) - _ERROR_MAX_COUNT
        if hidden_notes > 0:
            lines.append(f"  … +{_plural(hidden_notes, 'more note')}")
        return "\n".join(lines)

    def __str__(self) -> str:
        """The full assembled prompt text — exactly ``render_text(self)``."""
        return render_text(self)

    # -- properties ---------------------------------------------------------

    @property
    def text(self) -> str:
        """The assembled prompt text (``render_text(self)``).

        Examples:
            >>> from attachments.types import make_artifact
            >>> a = Artifacts([make_artifact(text="hi", meta={"source": "a.txt"})])
            >>> a.text
            '## a.txt\\nhi'
            >>> a.text == str(a)
            True
        """
        return render_text(self)

    @property
    def tokens(self) -> int:
        """Estimated token count over all artifact text.

        A FAST APPROXIMATION, not a tokenizer: total artifact text
        characters divided by 4, rounded up (``ceil(chars / 4)``). Real
        token counts vary by model and content; use this for quick
        budget checks, not billing math.

        Examples:
            >>> from attachments.types import make_artifact
            >>> Artifacts([]).tokens
            0
            >>> Artifacts([make_artifact(text="abcd")]).tokens
            1
            >>> Artifacts([make_artifact(text="abcde")]).tokens
            2
            >>> Artifacts([make_artifact(text="ab"), make_artifact(text="cd")]).tokens
            1
        """
        chars = sum(len(artifact.get("text") or "") for artifact in self)
        return -(-chars // 4)  # ceil(chars / 4) without importing math

    @property
    def images(self) -> list[dict]:
        """Flattened list of ImageItem dicts across all artifacts.

        Examples:
            >>> from attachments.types import make_artifact
            >>> img = {"name": "p.png", "mimetype": "image/png", "bytes": b""}
            >>> a = Artifacts([make_artifact(images=[img]), make_artifact()])
            >>> [i["name"] for i in a.images]
            ['p.png']
        """
        return [image for artifact in self for image in (artifact.get("images") or [])]

    @property
    def errors(self) -> list[dict]:
        """``{"source", "code", "message"}`` dicts for artifacts with errors.

        Examples:
            >>> from attachments.types import error_artifact, make_artifact
            >>> a = Artifacts(
            ...     [
            ...         make_artifact(text="fine"),
            ...         error_artifact("f.pdf", "parse-error", "bad"),
            ...     ]
            ... )
            >>> a.errors
            [{'source': 'f.pdf', 'code': 'parse-error', 'message': 'bad'}]
        """
        out: list[dict] = []
        for artifact in self:
            meta = artifact.get("meta") or {}
            error = meta.get("error")
            if isinstance(error, dict):
                out.append(
                    {
                        "source": meta.get("source") or "(unknown)",
                        "code": error.get("code") or "",
                        "message": error.get("message") or "",
                    }
                )
        return out

    # -- last-mile shortcuts (sugar over attachments.render) -----------------

    def claude(self, prompt: str | None = None) -> list[dict[str, Any]]:
        """Claude Messages API ``messages`` (see ``render.to_claude_messages``).

        Examples:
            >>> from attachments.types import make_artifact
            >>> a = Artifacts([make_artifact(text="hi", meta={"source": "a.txt"})])
            >>> [b["type"] for b in a.claude("Summarize.")[0]["content"]]
            ['text', 'text']
            >>> [b["type"] for b in a.claude()[0]["content"]]
            ['text']
        """
        return to_claude_messages(self, prompt=prompt)

    def openai(self, prompt: str | None = None) -> list[dict[str, Any]]:
        """OpenAI Chat Completions ``messages`` (``render.to_openai_messages``).

        Examples:
            >>> from attachments.types import make_artifact
            >>> a = Artifacts([make_artifact(text="hi", meta={"source": "a.txt"})])
            >>> [p["type"] for p in a.openai("Go")[0]["content"]]
            ['text', 'text']
            >>> [p["type"] for p in a.openai()[0]["content"]]
            ['text']
        """
        return to_openai_messages(self, prompt=prompt)

    def chunk(self, **kwargs: Any) -> list[str]:
        """Segment-aware RAG chunks (see ``render.chunk``).

        Examples:
            >>> from attachments.types import make_artifact
            >>> a = Artifacts(
            ...     [make_artifact(text="alpha beta", meta={"source": "a.txt"})]
            ... )
            >>> a.chunk(max_chars=6, overlap=0)
            ['## a.txt\\nalpha ', '## a.txt\\nbeta']
        """
        return _chunk(self, **kwargs)

    # -- list behavior that stays in the family ------------------------------

    def __getitem__(self, index):  # type: ignore[override]
        """Slices return ``Artifacts``; a single index returns the dict as-is.

        Examples:
            >>> from attachments.types import make_artifact
            >>> a = Artifacts([make_artifact(text="x"), make_artifact(text="y")])
            >>> type(a[0:1]).__name__
            'Artifacts'
            >>> type(a[0]).__name__
            'dict'
        """
        result = super().__getitem__(index)
        if isinstance(index, slice):
            return Artifacts(result)
        return result

    def __add__(self, other):  # type: ignore[override]
        """``att(a) + att(b)`` composes into one ``Artifacts``.

        Examples:
            >>> from attachments.types import make_artifact
            >>> a = Artifacts([make_artifact(text="x")])
            >>> b = Artifacts([make_artifact(text="y")])
            >>> combined = a + b
            >>> type(combined).__name__, len(combined)
            ('Artifacts', 2)
        """
        if not isinstance(other, list):
            return NotImplemented
        return Artifacts(list.__add__(self, other))

    def __radd__(self, other):
        """Plain ``list + Artifacts`` also lands in the family.

        Examples:
            >>> from attachments.types import make_artifact
            >>> a = Artifacts([make_artifact(text="y")])
            >>> type([make_artifact(text="x")] + a).__name__
            'Artifacts'
        """
        if not isinstance(other, list):
            return NotImplemented
        return Artifacts(list.__add__(other, self))

    # -- Jupyter ------------------------------------------------------------

    def _repr_markdown_(self) -> str:
        """Markdown for Jupyter: summary, error admonitions, preview, thumbs.

        Shows the summary heading, one ``> ⚠️`` admonition per error —
        identical error content collapses into one admonition suffixed
        ``(xN)``, like ``__repr__`` — (UNIQUE admonitions capped at
        ``_ERROR_MAX_COUNT``, the rest noted as ``+N more
        errors — see .errors``), the first ~600 chars of the assembled
        text in a fenced block (the fence is always longer than any
        backtick run in the preview, so content containing ``` cannot
        break out and render as live markdown), and up to 4 inline image
        thumbnails (data URLs) — only images whose decoded payload is
        <= 1 MiB each; the rest are noted as ``+N more images``.
        Wire-form images (``bytes_b64``) work too. No heavy imports.

        Examples:
            >>> from attachments.types import make_artifact
            >>> img = {"name": "p.png", "mimetype": "image/png", "bytes": b"\\x89P"}
            >>> a = Artifacts(
            ...     [make_artifact(text="hi", images=[img], meta={"source": "a"})]
            ... )
            >>> md = a._repr_markdown_()
            >>> "### Artifacts — 1 artifact | 2 chars | ~1 tokens | 1 image" in md
            True
            >>> "![p.png](data:image/png;base64," in md
            True
        """
        parts = [f"### Artifacts — {self._summary()}"]
        error_lines = _collapse_lines(
            [
                (
                    f"`{error['source']}`",
                    f"{error['code']} — {_clip_message(error['message'])}",
                )
                for error in self.errors
            ]
        )
        parts.extend(f"> ⚠️ {line}" for line in error_lines[:_ERROR_MAX_COUNT])
        hidden = len(error_lines) - _ERROR_MAX_COUNT
        if hidden > 0:
            parts.append(f"> … +{_plural(hidden, 'more error')} — see `.errors`")
        text = self.text
        if text:
            preview = text[:_PREVIEW_CHARS]
            fence = _fence(preview)
            block = f"{fence}text\n{preview}\n{fence}"
            remaining = len(text) - len(preview)
            if remaining > 0:
                block += f"\n… ({remaining:,} more chars)"
            parts.append(block)
        thumbnails: list[str] = []
        images = self.images
        for image in images:
            if len(thumbnails) >= _THUMBNAIL_MAX_COUNT:
                break
            data = _image_payload_b64(image)
            if data is None:
                continue
            name = image.get("name") or "image"
            mimetype = image.get("mimetype") or "application/octet-stream"
            thumbnails.append(f"![{name}](data:{mimetype};base64,{data})")
        if thumbnails:
            parts.append("\n".join(thumbnails))
        more = len(images) - len(thumbnails)
        if more > 0:
            parts.append(f"+{_plural(more, 'more image')}")
        return "\n\n".join(parts)
