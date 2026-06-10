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
    """
    filename = options.get("filename", "page.html")

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

    # Optionally prefix with title (only if not already present)
    if title and title not in text:
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
)
register_processor(".html", html_processor)
register_processor(".htm", html_processor)
register_options(".html", _HTML_OPTIONS)
register_options(".htm", _HTML_OPTIONS)
