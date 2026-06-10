"""Processor for raster images (.png, .jpg, .jpeg, .gif, .webp, .bmp, .tiff, .heic).

Identifies the image with Pillow and emits a single ImageItem. Web-friendly
formats (png/jpeg/gif/webp) pass through untouched; exotic formats (bmp,
tiff, heic, ...) are re-encoded to PNG; an optional ``max_dim`` downscales
the longest side while preserving the aspect ratio, and an optional
``rotate`` turns the image counterclockwise (applied before ``max_dim``).

Requires Pillow: ``pip install attachments[image]``
HEIC/HEIF additionally requires pillow-heif: ``pip install attachments[heic]``
"""

from __future__ import annotations

import io
from typing import Any

from .._options import Option, register_options
from ..types import (
    ERROR_PARSE,
    ERROR_PROCESSING,
    error_artifact,
    make_artifact,
    missing_dep_artifact,
)
from . import register_processor

#: Formats served as-is (original bytes + mimetype) when no resize is needed.
_PASSTHROUGH = {
    "PNG": ("image/png", "png"),
    "JPEG": ("image/jpeg", "jpg"),
    "GIF": ("image/gif", "gif"),
    "WEBP": ("image/webp", "webp"),
}

#: Image modes each encoder accepts; anything else is converted to RGB first.
_ENCODABLE_MODES = {
    "PNG": ("1", "L", "LA", "P", "RGB", "RGBA"),
    "JPEG": ("L", "RGB", "CMYK"),
}


def _looks_heic(data: bytes, filename: str | None) -> bool:
    """Cheap HEIC/HEIF detection: extension or ISO-BMFF ftyp brand sniff."""
    if filename and filename.lower().rsplit(".", 1)[-1] in ("heic", "heif"):
        return True
    return data[4:8] == b"ftyp" and data[8:12].startswith((b"hei", b"mif1", b"msf1"))


def image_processor(
    data: bytes,
    *,
    filename: str | None = None,
    max_dim: int | None = None,
    rotate: int | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Convert image bytes to an artifact carrying one ImageItem.

    Options:
        filename: Original filename (used for metadata and the image name).
        max_dim: Downscale so the longest side is at most this many pixels.
        rotate: Rotate counterclockwise by this many degrees (PIL-native
            direction; negative values rotate clockwise). Normalized modulo
            360; applied before ``max_dim``. ``expand=True`` grows the canvas,
            so non-right angles get background fill in the corners.

    Behavior:
        - png/jpeg/gif/webp with no resize/rotate needed: bytes pass through.
        - ``max_dim`` exceeded or nonzero ``rotate``: transform and re-encode —
          JPEG (quality 85) when the original was JPEG, PNG otherwise.
        - Exotic formats (bmp/tiff/heic/...): re-encode to PNG.

    Never raises: corrupt bytes yield a ``parse-error`` artifact and a
    missing Pillow (or pillow-heif for HEIC inputs) yields the typed
    ``missing-dependency`` artifact.
    """
    source = filename or "image"

    # HEIC needs pillow-heif registered with Pillow *before* Image.open. This
    # branch runs only for HEIC inputs so a missing pillow_heif never affects
    # png/jpg processing. The heic extra implies both modules, so a missing
    # PIL is also reported as feature "heic" for these inputs.
    is_heic = _looks_heic(data, filename)
    if is_heic:
        try:
            from pillow_heif import register_heif_opener

            register_heif_opener()  # idempotent, safe to call per-request
        except ImportError:
            return missing_dep_artifact(source, "heic")

    try:
        from PIL import Image
    except ImportError:
        return missing_dep_artifact(source, "heic" if is_heic else "image")

    try:
        img = Image.open(io.BytesIO(data))
        img.load()  # force a full decode so truncated/corrupt files fail here
    except Exception as e:
        return error_artifact(source, ERROR_PARSE, f"Failed to parse image: {e}")

    # Capture identity before any transform (thumbnail/convert clear .format).
    original_format = (img.format or "unknown").upper()
    mode = img.mode

    try:
        degrees = 0 if rotate is None else int(rotate) % 360
        if degrees:
            # PIL-native counterclockwise; expand=True grows the canvas so
            # nothing is cropped (non-right angles get corner fill).
            img = img.rotate(degrees, expand=True)

        limit = None if max_dim is None else int(max_dim)
        resized = limit is not None and max(img.size) > limit

        if not resized and not degrees and original_format in _PASSTHROUGH:
            mimetype, ext = _PASSTHROUGH[original_format]
            name = filename or f"image.{ext}"
            image_bytes = data
        else:
            if resized:
                img.thumbnail((limit, limit))  # in-place, preserves aspect
            # Keep it simple: JPEG stays JPEG (quality 85), everything else PNG.
            out_format = "JPEG" if original_format == "JPEG" else "PNG"
            if img.mode not in _ENCODABLE_MODES[out_format]:
                img = img.convert("RGB")
            buf = io.BytesIO()
            save_kwargs: dict[str, Any] = (
                {"quality": 85} if out_format == "JPEG" else {}
            )
            img.save(buf, format=out_format, **save_kwargs)
            image_bytes = buf.getvalue()
            mimetype, ext = (
                ("image/jpeg", "jpg") if out_format == "JPEG" else ("image/png", "png")
            )
            stem = source.rsplit(".", 1)[0] if "." in source else source
            name = f"{stem}.{ext}"

        width, height = img.size  # post-resize dimensions
        extra: dict[str, Any] = {
            "width": width,
            "height": height,
            "original_format": original_format,
            "mode": mode,
        }
        if resized:
            extra["resized"] = True
        if degrees:
            extra["rotated"] = degrees

        return make_artifact(
            text="",
            images=[{"name": name, "mimetype": mimetype, "bytes": image_bytes}],
            meta={"kind": "image", "extra": extra},
        )
    except Exception as e:
        return error_artifact(source, ERROR_PROCESSING, f"Failed to process image: {e}")


#: Extensions handled by this processor.
EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".tiff",
    ".tif",
    ".heic",
    ".heif",
)

#: Declared option schema (see attachments.options).
OPTIONS = (
    Option(
        name="max_dim",
        type="int",
        help="Downscale so the longest side is at most this many pixels",
        example="max_dim: 1024",
    ),
    Option(
        name="rotate",
        type="int",
        help="Rotate counterclockwise by this many degrees (negative = clockwise)",
        example="rotate: 90",
    ),
)


def register() -> None:
    """Register the image processor and its option schema (idempotent)."""
    for ext in EXTENSIONS:
        register_processor(ext, image_processor)
        register_options(ext, OPTIONS)


register()
