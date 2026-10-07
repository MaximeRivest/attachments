"""Shared output controls for processors that emit images (pdf, image).

One meaning for ``max_dim``, ``image_format`` and ``quality`` wherever
they are declared, so ``report.pdf[max_dim: 1568, image_format: jpeg]``
and ``photo.png[max_dim: 1568, image_format: jpeg]`` behave alike.

Pillow is imported lazily, only by :func:`pil_encode` (the pdf processor's
PyMuPDF path never needs it).
"""

from __future__ import annotations

import io
from typing import Any

#: Accepted ``image_format`` values -> (Pillow format, mimetype, extension).
FORMATS: dict[str, tuple[str, str, str]] = {
    "png": ("PNG", "image/png", "png"),
    "jpeg": ("JPEG", "image/jpeg", "jpg"),
    "jpg": ("JPEG", "image/jpeg", "jpg"),
}

#: JPEG quality used when none is given (Pillow's own default is 75; 85 keeps
#: page text crisp). JPEG is not always smaller: on clean text pages PNG often
#: wins; on scans and photos JPEG is several times smaller.
DEFAULT_QUALITY = 85

#: Highest accepted quality: Pillow advises against values above 95
#: (100 disables parts of the JPEG compression for little visible gain).
MAX_QUALITY = 95


def check_image_output(
    *,
    max_dim: Any = None,
    image_format: Any = None,
    quality: Any = None,
) -> str | None:
    """Return an ``invalid-option`` message for bad values, else ``None``.

    ``max_dim`` must be an integer >= 0 (0 means no limit); ``image_format``
    one of png/jpeg/jpg; ``quality`` an integer from 1 to 95.

    Examples:
        >>> check_image_output(max_dim=1568, image_format="JPEG", quality=80) is None
        True
        >>> check_image_output(image_format="gif")
        "image_format must be png or jpeg, got 'gif'"
        >>> check_image_output(quality=100)
        'quality must be an integer from 1 to 95, got 100'
        >>> check_image_output(max_dim=-1)
        'max_dim must be an integer >= 0 (0 = no limit), got -1'
    """
    if max_dim is not None and (
        isinstance(max_dim, bool) or not isinstance(max_dim, int) or max_dim < 0
    ):
        return f"max_dim must be an integer >= 0 (0 = no limit), got {max_dim!r}"
    if image_format is not None and str(image_format).lower() not in FORMATS:
        return f"image_format must be png or jpeg, got {image_format!r}"
    if quality is not None and (
        isinstance(quality, bool)
        or not isinstance(quality, int)
        or not 1 <= quality <= MAX_QUALITY
    ):
        return f"quality must be an integer from 1 to {MAX_QUALITY}, got {quality!r}"
    return None


def output_format(image_format: str) -> tuple[str, str, str]:
    """``(pillow_format, mimetype, extension)`` for a checked *image_format*.

    Examples:
        >>> output_format("JPG")
        ('JPEG', 'image/jpeg', 'jpg')
    """
    return FORMATS[str(image_format).lower()]


def limit(max_dim: int | None) -> int | None:
    """Normalize ``max_dim``: ``None`` and ``0`` both mean no limit.

    Examples:
        >>> limit(0) is None, limit(None) is None, limit(1568)
        (True, True, 1568)
    """
    return max_dim or None


def pil_encode(img: Any, pillow_format: str, quality: int | None = None) -> bytes:
    """Encode a Pillow image as PNG or JPEG.

    JPEG has no transparency: transparent pixels are flattened onto white
    (converting straight to RGB would turn them black, often hiding dark
    text drawn on a transparent background). Other modes JPEG/PNG cannot
    store are converted to RGB.
    """
    from PIL import Image

    if pillow_format == "JPEG":
        has_alpha = img.mode in ("RGBA", "LA", "PA") or (
            img.mode == "P" and "transparency" in img.info
        )
        if has_alpha:
            rgba = img.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.getchannel("A"))
            img = background
        elif img.mode not in ("L", "RGB", "CMYK"):
            img = img.convert("RGB")
        save_kwargs: dict[str, Any] = {
            "quality": quality or DEFAULT_QUALITY,
            "optimize": True,
        }
    else:
        if img.mode not in ("1", "L", "LA", "P", "RGB", "RGBA"):
            img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
        save_kwargs = {}
    buf = io.BytesIO()
    img.save(buf, format=pillow_format, **save_kwargs)
    return buf.getvalue()
