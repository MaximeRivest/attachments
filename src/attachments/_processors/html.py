"""Processor for HTML files (.html, .htm).

Extracts visible text using BeautifulSoup, stripping scripts/styles.
Returns a typed missing-dependency artifact when bs4 is not installed.
Requires ``beautifulsoup4`` + ``lxml``: ``pip install attachments[html]``
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .._options import Option, register_options
from ..types import ERROR_PARSE, error_artifact, make_artifact, missing_dep_artifact
from . import register_processor

log = logging.getLogger("attachments.processors.html")

# Tags whose content is never useful as "text"
_STRIP_TAGS = frozenset(["script", "style", "noscript", "svg", "math", "template"])


def _collapse_whitespace(text: str) -> str:
    """Collapse runs of whitespace while preserving paragraph breaks."""
    # Normalise line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse blank-line runs to a single blank line
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Collapse horizontal whitespace within lines
    lines = []
    for line in text.split("\n"):
        lines.append(re.sub(r"[ \t]+", " ", line).strip())
    return "\n".join(lines).strip()


def _extract_title(soup) -> str | None:
    """Extract <title> text if present."""
    tag = soup.find("title")
    if tag:
        return tag.get_text(strip=True)
    return None


def html_processor(data: bytes, **options: Any) -> dict[str, Any]:
    """Convert HTML bytes to an artifact.

    Options:
        filename: Original filename (for metadata).
        images: If ``True``, extract ``<img src="data:...">``
            inline images (default ``False``).
        select: CSS selector string; when provided, only matching
            elements (in document order) contribute text/images. The
            title is still recorded in ``extra.title`` but is NOT
            prefixed to the text. No-match and invalid selectors are
            not errors: the artifact has ``text == ""`` plus an
            explanatory ``extra.select_note``.

    DSL note: the v3 parser takes the final *balanced* bracket group,
    so attribute selectors work inline — ``page.html[select: a[href]]``.
    Comma groups must be quoted in DSL (``[select: "h1, p"]``): segments
    split on commas outside quotes, and a segment without a colon (like
    the bare ``p`` in ``[select: h1,p]``) invalidates the WHOLE bracket
    group, which then stays in the source and is misrouted as a glob
    pattern. The kwargs twin (``att(..., select="h1, p")``) always works.

    Examples:
        >>> art = html_processor(
        ...     b"<html><head><title>T</title></head>"
        ...     b"<body><h1>Top</h1><p>Body</p></body></html>",
        ...     select="h1",
        ... )
        >>> art["text"]
        'Top'
        >>> art["meta"]["extra"]["selected_count"]
        1
        >>> bad = html_processor(b"<p>x</p>", select="li:::")
        >>> bad["text"], bad["meta"]["extra"]["selected_count"]
        ('', 0)
    """
    filename = options.get("filename", "page.html")
    selector = options.get("select")

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return missing_dep_artifact(filename, "html")

    # Pick the best available parser
    try:
        import lxml  # noqa: F401

        parser = "lxml"
    except ImportError:
        parser = "html.parser"

    try:
        soup = BeautifulSoup(data, parser)
    except Exception as e:
        log.warning("failed to parse HTML %s: %s", filename, e)
        return error_artifact(filename, ERROR_PARSE, f"Failed to parse HTML: {e}")

    title = _extract_title(soup)

    # --- CSS selection (runs on the FULL soup, scripts intact) ---
    select_extra: dict[str, Any] = {}
    select_active = False
    if isinstance(selector, str) and selector.strip():
        selector = selector.strip()
        select_active = True
        select_extra["selector"] = selector
        try:
            matches = soup.select(selector)
        except Exception as e:  # soupsieve SelectorSyntaxError on garbage
            matches = []
            select_extra["select_note"] = f"invalid selector: {e}"
        select_extra["selected_count"] = len(matches)
        if len(matches) == 0:
            select_extra.setdefault("select_note", "selector matched no elements")
            soup = BeautifulSoup("", parser)
        elif len(matches) == 1:
            soup = BeautifulSoup(str(matches[0]), parser)
        else:
            soup = BeautifulSoup(
                "<div>" + "".join(str(e) for e in matches) + "</div>", parser
            )

    # Remove non-visible elements
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()

    # Remove <head> entirely — we already captured the title
    head = soup.find("head")
    if head:
        head.decompose()

    # Extract text with newlines at block boundaries
    raw_text = soup.get_text(separator="\n")
    text = _collapse_whitespace(raw_text)

    # Optionally prefix with title (only if not already present).
    # Skipped when select is active: selection text must be exactly
    # the selection (title is still in extra.title).
    if title and not select_active and title not in text:
        text = f"{title}\n\n{text}"

    # --- inline data-URI images ---
    import base64

    images: list[dict[str, Any]] = []
    extract_images = bool(options.get("images") or options.get("render_images"))
    if extract_images:
        for i, img_tag in enumerate(soup.find_all("img")):
            src = img_tag.get("src", "")
            if src.startswith("data:"):
                try:
                    header, b64 = src.split(",", 1)
                    mime = header.split(";")[0].replace("data:", "")
                    ext = mime.split("/")[-1].split("+")[0] or "png"
                    images.append(
                        {
                            "name": f"{filename}-img-{i + 1}.{ext}",
                            "mimetype": mime,
                            "bytes": base64.b64decode(b64),
                        }
                    )
                except Exception as exc:
                    log.debug("skipping data-URI image %d: %s", i, exc)

    return make_artifact(
        text=text,
        images=images,
        meta={
            "kind": "html",
            "extra": {
                "filename": filename,
                "title": title,
                "parser": parser,
                "chars": len(text),
                **select_extra,
            },
        },
    )


# Override the plain-text registration for .html / .htm
_HTML_OPTIONS = (
    Option(
        "images",
        "bool",
        aliases=("render",),
        param="render_images",
        default=False,
        help="Extract inline data-URI images.",
        example="images: true",
    ),
    Option(
        "select",
        "str",
        aliases=("css",),
        help="CSS selector; extract only matching elements",
        example='select: "h1, .article"',
    ),
)
register_processor(".html", html_processor)
register_processor(".htm", html_processor)
register_options(".html", _HTML_OPTIONS)
register_options(".htm", _HTML_OPTIONS)
