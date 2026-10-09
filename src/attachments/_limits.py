"""Provider request limits, checked when ``.claude()`` / ``.openai()`` build
a request, so a request that would be rejected says why, with the fix,
before it is sent.

A warning (:class:`RequestLimitWarning`), not an error: the same request
may go to a gateway or a platform with other limits, and a limit can
change before this library does. Silence it with
``warnings.filterwarnings("ignore", category=RequestLimitWarning)``.

Limits as published (read 2026-10-09):

- Claude: docs.claude.com/en/api/overview (request size) and
  docs.claude.com/en/docs/build-with-claude/vision (images).
- OpenAI: developers.openai.com/api/docs/guides/images-vision.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import sys
import warnings
from dataclasses import dataclass
from typing import Any

from ._imagesize import image_size

__all__ = ["RequestLimitWarning", "CLAUDE", "OPENAI", "check_request"]


class RequestLimitWarning(UserWarning):
    """A request built by ``.claude()`` / ``.openai()`` breaks a published limit."""


@dataclass(frozen=True)
class Limits:
    """One provider's published limits for a single request."""

    provider: str
    request_bytes: int
    request_note: str
    images: int
    images_note: str
    image_b64_bytes: int | None = None
    image_note: str = ""
    max_side: int | None = None
    many_images: int | None = None  # above this many images ...
    many_side: int | None = None  # ... each side must be at most this
    media_types: frozenset[str] = frozenset(
        {"image/jpeg", "image/png", "image/gif", "image/webp"}
    )


CLAUDE = Limits(
    provider="Claude",
    request_bytes=32_000_000,
    request_note="Bedrock: 20 MB, Google Cloud: 30 MB",
    images=100,
    images_note="100 for models with a 200k-token context, 600 for others",
    image_b64_bytes=10_000_000,
    image_note="5 MB on Bedrock and Google Cloud",
    max_side=8000,
    many_images=20,
    many_side=2000,
)

OPENAI = Limits(
    provider="OpenAI",
    request_bytes=512_000_000,
    request_note="",
    images=1500,
    images_note="",
)

#: Bytes of base64 decoded to find a picture's size in its header; JPEG
#: headers can sit after large metadata, so the whole picture is the
#: fallback.
_HEADER_B64 = 87_384  # 64 KiB decoded


def _mb(n: int) -> str:
    return f"{n / 1e6:.1f} MB"


def _size(data: str) -> tuple[int, int] | None:
    try:
        size = image_size(base64.b64decode(data[:_HEADER_B64]))
        return size if size is not None else image_size(base64.b64decode(data))
    except (binascii.Error, ValueError):
        return None


def request_problems(parts: list[dict[str, Any]], limits: Limits) -> list[str]:
    """What in the neutral *parts* (see ``render.to_parts``) breaks *limits*.

    Each problem is one sentence; the last line, when there are problems,
    says how to fix them. ``[]`` when the request fits.

    Examples:
        >>> request_problems([{"type": "text", "text": "hi"}], CLAUDE)
        []
        >>> big = {"type": "image", "media_type": "image/png", "data": "A" * 33_000_000}
        >>> print("\\n".join(request_problems([big], CLAUDE)))  # doctest: +ELLIPSIS
        the request is 33.0 MB; Claude accepts 32.0 MB (Bedrock: 20 MB, ...)
        a picture is 33.0 MB (base64); Claude accepts 10.0 MB (5 MB on ...)
        Fix: image_format: jpeg (...); max_dim: 1568 (...)
        >>> bmp = {"type": "image", "media_type": "image/bmp", "data": "Qk0="}
        >>> for line in request_problems([bmp], OPENAI):
        ...     print(line)
        a picture is image/bmp; OpenAI accepts gif, jpeg, png, webp
        Fix: image_format: png (converts the picture)
    """
    images = [p for p in parts if p.get("type") == "image"]
    texts = [p for p in parts if p.get("type") == "text"]
    picture_bytes = sum(len(p.get("data") or "") for p in images)
    # Each block's JSON wrapper is ~100 bytes; the envelope ~200.
    total = picture_bytes + sum(len(json.dumps(p.get("text") or "")) for p in texts)
    total += 100 * len(parts) + 200

    problems: list[str] = []
    note = f" ({limits.request_note})" if limits.request_note else ""
    if total > limits.request_bytes:
        problems.append(
            f"the request is {_mb(total)}; {limits.provider} accepts "
            f"{_mb(limits.request_bytes)}{note}"
        )
    if len(images) > limits.images:
        note = f" ({limits.images_note})" if limits.images_note else ""
        problems.append(
            f"it has {len(images)} pictures; {limits.provider} accepts "
            f"{limits.images}{note}"
        )
    if limits.image_b64_bytes is not None:
        too_big = [
            p for p in images if len(p.get("data") or "") > limits.image_b64_bytes
        ]
        if too_big:
            largest = max(len(p["data"]) for p in too_big)
            note = f" ({limits.image_note})" if limits.image_note else ""
            what = (
                "a picture is"
                if len(too_big) == 1
                else f"{len(too_big)} pictures are up to"
            )
            problems.append(
                f"{what} {_mb(largest)} (base64); {limits.provider} accepts "
                f"{_mb(limits.image_b64_bytes)}{note}"
            )
    odd = sorted({p.get("media_type") for p in images} - limits.media_types - {None})
    if odd:
        problems.append(
            f"a picture is {', '.join(odd)}; {limits.provider} accepts "
            f"{', '.join(sorted(t.split('/')[-1] for t in limits.media_types))}"
        )
    if limits.max_side is not None:
        many = limits.many_images is not None and len(images) > limits.many_images
        side = limits.many_side if many and limits.many_side else limits.max_side
        sizes = [s for p in images if (s := _size(p.get("data") or ""))]
        over = [s for s in sizes if max(s) > side]
        if over:
            biggest = max(over, key=max)
            why = (
                f" when a request has more than {limits.many_images} pictures"
                if many and side == limits.many_side
                else ""
            )
            problems.append(
                f"{len(over)} picture(s) up to {biggest[0]}x{biggest[1]} px; "
                f"{limits.provider} accepts {side} px a side{why}"
            )
    if not problems:
        return []

    size_problem = any(
        p.startswith(("the request is", "a picture is ", "pictures are")) and "MB" in p
        for p in problems
    ) or any(" px; " in p for p in problems)
    count_problem = len(images) > limits.images
    fixes = []
    if size_problem:
        png = sum(len(p["data"]) for p in images if p.get("media_type") == "image/png")
        if png > picture_bytes / 2:
            fixes.append("image_format: jpeg (scans and photos several times smaller)")
        fixes.append("max_dim: 1568 (Claude's standard models see no more)")
    if count_problem or (size_problem and len(images) > 1):
        half = max(1, min(len(images), limits.images) // 2)
        fixes.append(f"fewer pages per request, e.g. pages: 1-{half}")
    if odd:
        fixes.append("image_format: png (converts the picture)")
    if fixes:
        problems.append("Fix: " + "; ".join(fixes))
    return problems


def _caller_stacklevel() -> int:
    """stacklevel pointing at the first frame outside this package."""
    package = os.path.dirname(os.path.abspath(__file__))
    level, frame = 1, sys._getframe(1)
    while frame is not None and os.path.abspath(frame.f_code.co_filename).startswith(
        package
    ):
        frame = frame.f_back
        level += 1
    return level


def check_request(parts: list[dict[str, Any]], limits: Limits) -> None:
    """Warn (:class:`RequestLimitWarning`) when *parts* break *limits*."""
    problems = request_problems(parts, limits)
    if problems:
        body = "\n".join(
            f"  - {p}" if not p.startswith("Fix:") else f"  {p}" for p in problems
        )
        warnings.warn(
            f"This {limits.provider} request would be rejected:\n{body}",
            RequestLimitWarning,
            stacklevel=_caller_stacklevel(),
        )
