"""Processor for SVG vector images (.svg, .svgz).

Always works with the stdlib: parses the XML and extracts human-readable
text (``<title>``, ``<desc>``, ``<text>``, ``<tspan>``, ``<textPath>``) in
document order, namespace-agnostically. Gzip-compressed SVG (``.svgz`` or
gzip magic bytes under any extension) is transparently decompressed —
fixing the v1 bug where gzip bytes were read as text and produced an
"Error loading SVG" artifact.

Rasterization to PNG is opt-in via ``images: true`` (or ``auto``) and uses
cairosvg when installed: ``pip install attachments[svg]``. Per spec, the
typed missing-dependency artifact fires only on explicit request
(``true``/``always``); ``auto`` silently keeps the text artifact.

Deliberately dropped v1 behaviors:
    - The uniform-color "did cairosvg fail?" heuristic plus the Playwright
      browser and wand/ImageMagick fallbacks (heavy undeclared deps,
      nondeterministic, false-positives on legitimately solid images).
    - Embedding raw ``data:image/svg+xml`` URLs when no renderer exists
      (v3 consumers expect raster mimetypes; the text path plus the typed
      missing-dep artifact covers it).
    - ``[format:]`` presenter aliases (the render layer owns presentation).
    - EPS support entirely (deferred).
"""

from __future__ import annotations

import gzip
import logging
import xml.etree.ElementTree as ET
from typing import Any

from .._options import Option, register_options
from ..types import ERROR_PARSE, error_artifact, make_artifact, missing_dep_artifact
from . import register_processor

log = logging.getLogger("attachments.processors.svg")

#: Local (namespace-stripped) tag names whose text is human-readable.
_TEXT_TAGS = frozenset(["title", "desc", "text", "tspan", "textPath"])

#: Root attributes copied verbatim into ``meta.extra`` when present.
_ROOT_ATTRS = ("width", "height", "viewBox")


def _local(tag: object) -> str:
    """Return the namespace-free local name of an element tag.

    >>> _local("{http://www.w3.org/2000/svg}text")
    'text'
    >>> _local("desc")
    'desc'
    """
    return tag.split("}")[-1] if isinstance(tag, str) else ""


def _extract_text(root: ET.Element) -> list[str]:
    """Collect stripped text lines from text-bearing elements in document order."""
    lines: list[str] = []
    skip: set[int] = set()  # children of matched elements (avoid duplicates)
    for elem in root.iter():
        if id(elem) in skip:
            continue
        if _local(elem.tag) in _TEXT_TAGS:
            for child in elem.iter():
                if child is not elem:
                    skip.add(id(child))
            line = " ".join(t.strip() for t in elem.itertext() if t.strip())
            if line:
                lines.append(line)
    return lines


def svg_processor(
    data: bytes,
    *,
    filename: str | None = None,
    render_images: Any = False,
    **_: Any,
) -> dict[str, Any]:
    """Convert SVG bytes to an artifact (text always; PNG raster on request).

    Options:
        filename: Original filename (used for metadata and the image name).
        render_images: ``False`` (default) never rasters; ``True``/``"always"``
            requires cairosvg (typed missing-dependency artifact otherwise);
            ``"auto"`` rasters only when cairosvg imports.

    Never raises: malformed XML or bad gzip yields a ``parse-error``
    artifact; a missing cairosvg on explicit request yields the typed
    ``missing-dependency`` artifact.
    """
    source = filename or "image.svg"

    compressed = data[:2] == b"\x1f\x8b" or (
        filename is not None and filename.lower().endswith(".svgz")
    )
    if compressed:
        try:
            data = gzip.decompress(data)
        except Exception as e:
            return error_artifact(source, ERROR_PARSE, f"Failed to decompress SVG: {e}")

    try:
        root = ET.fromstring(data)
    except Exception as e:
        return error_artifact(source, ERROR_PARSE, f"Failed to parse SVG: {e}")

    lines = _extract_text(root)
    text = "\n".join(lines)

    extra: dict[str, Any] = {}
    for attr in _ROOT_ATTRS:
        if attr in root.attrib:
            extra[attr] = root.attrib[attr]
    extra["elements"] = sum(1 for _ in root.iter())
    extra["has_text"] = bool(lines)
    if compressed:
        extra["compressed"] = True

    meta: dict[str, Any] = {"kind": "vector", "extra": extra}
    images: list[dict[str, Any]] = []

    if render_images in (True, "always", "auto"):
        try:
            import cairosvg
        except ImportError:
            if render_images == "auto":
                extra["render_skipped"] = "cairosvg not installed"
                cairosvg = None
            else:
                return missing_dep_artifact(source, "svg")
        if cairosvg is not None:
            try:
                png_bytes = cairosvg.svg2png(bytestring=data)
                stem = source.rsplit(".", 1)[0] if "." in source else source
                images.append(
                    {
                        "name": f"{stem}.png",
                        "mimetype": "image/png",
                        "bytes": png_bytes,
                    }
                )
                extra["renderer"] = "cairosvg"
            except Exception as e:
                log.warning("rasterization failed for %s: %s", source, e)
                meta.setdefault("warnings", []).append(f"rasterization failed: {e}")

    return make_artifact(text=text, images=images, meta=meta)


#: Extensions handled by this processor.
EXTENSIONS = (".svg", ".svgz")

#: Declared option schema (see attachments.options).
OPTIONS = (
    Option(
        "images",
        "bool_or_auto",
        aliases=("render",),
        param="render_images",
        default=False,
        help="Rasterize the SVG to PNG with cairosvg (true/false/auto/always).",
        example="images: true",
    ),
)


def register() -> None:
    """Register the SVG processor and its option schema (idempotent)."""
    for ext in EXTENSIONS:
        register_processor(ext, svg_processor)
        register_options(ext, OPTIONS)


register()
