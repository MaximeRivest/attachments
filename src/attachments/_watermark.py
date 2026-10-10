"""Labels on pictures: the ``watermark`` option.

``report.pdf[images: true, watermark: page]`` writes "page 3" in a white
strip above the picture of page 3, so a model that sees many pictures
knows which is which, even when the text around them is cut away.

Every processor that makes pictures declares :data:`WATERMARK` in its
option schema (so ``att.options(".pdf")`` lists it and a text file warns
"Unknown option 'watermark'"). Core takes the value out before the
processor runs and calls :func:`apply_watermark` on the result, whether
the processor ran here or on the service: one implementation for every
format.

Choices, and why:

- **A strip above the picture, never on it.** A label drawn over the
  content can hide the very thing the model needs to read.
- **The picture keeps its size.** The content is scaled down to make room
  (a few percent), so ``max_dim`` and token estimates stay true. Only a
  picture too small to share its height (under ~4 strip heights) grows
  instead.
- **Off by default, and the file name only when asked** (``name``):
  0.25 stamped the file name on every picture, which told the model the
  name even with ``sources=False``.

Pillow is imported lazily, only when a label is drawn.
"""

from __future__ import annotations

import io
import os
from typing import Any
from urllib.parse import urlsplit

from ._options import Option

#: The declared option (shared by every processor that makes pictures).
WATERMARK = Option(
    name="watermark",
    type="str",
    help=(
        "Label each picture in a strip above it: page (its page, slide or "
        "sheet), name (file name and page), or your own text ({name} and "
        "{page} are filled in). Off by default."
    ),
    example="watermark: page",
)

#: Values that turn the label off.
_OFF = {"", "false", "no", "off", "none"}

#: Values meaning "file name and page" (``auto`` was 0.25's spelling).
_NAME = {"name", "true", "yes", "on", "auto"}

#: Template for :data:`_NAME`, kept in ``meta.extra.watermark``.
NAME_TEMPLATE = "{name} · {page}"

#: Template for ``page``.
PAGE_TEMPLATE = "{page}"

#: 0.25's ``text|position|style`` words (the label now always goes above).
_LEGACY_LAYOUT = {
    "bottom-right",
    "bottom-left",
    "top-right",
    "top-left",
    "center",
    "small",
    "medium",
    "large",
}


def split_legacy(value: Any) -> tuple[Any, bool]:
    """0.25's ``text|position|style`` -> ``(text, True)``; else ``(value, False)``.

    Examples:
        >>> split_legacy("Draft|bottom-left|large")
        ('Draft', True)
        >>> split_legacy("A|B"), split_legacy("page")
        (('A|B', False), ('page', False))
    """
    if not isinstance(value, str) or "|" not in value:
        return value, False
    text, *rest = (part.strip() for part in value.split("|"))
    if rest and all(part.lower() in _LEGACY_LAYOUT for part in rest):
        return text, True
    return value, False


_INK = (34, 34, 34)
_RULE = (200, 200, 200)
_PAPER = (255, 255, 255)


def template_for(value: Any) -> str | None:
    """The label template for a ``watermark`` value, or ``None`` (off).

    Examples:
        >>> template_for("page"), template_for("Name"), template_for(True)
        ('{page}', '{name} · {page}', '{name} · {page}')
        >>> template_for("off") is None, template_for(False) is None
        (True, True)
        >>> template_for("Draft {page}")
        'Draft {page}'
    """
    if value is None or value is False:
        return None
    text = str(value).strip()
    lowered = text.lower()
    if lowered in _OFF:
        return None
    if lowered in _NAME:
        return NAME_TEMPLATE
    if lowered == "page":
        return PAGE_TEMPLATE
    return text


def shows_name(meta: dict) -> bool:
    """Whether a picture label of this artifact contains its file name.

    Examples:
        >>> shows_name({"extra": {"watermark": "{name} · {page}"}})
        True
        >>> shows_name({"extra": {"watermark": "{page}"}}), shows_name({})
        (False, False)
    """
    template = ((meta or {}).get("extra") or {}).get("watermark")
    return isinstance(template, str) and "{name}" in template


def display_name(source: str) -> str:
    """The short name a label shows for *source* (a path or an address).

    Examples:
        >>> display_name("reports/2024/q3.pdf")
        'q3.pdf'
        >>> display_name("https://example.com/files/deck.pptx?x=1")
        'deck.pptx'
        >>> display_name("https://example.com/")
        'example.com'
    """
    if "://" in source:
        parts = urlsplit(source)
        tail = parts.path.rstrip("/").rsplit("/", 1)[-1]
        return tail or parts.netloc or source
    return os.path.basename(source.rstrip("/\\")) or source


def page_label(image: dict, artifact: dict) -> str:
    """Where *image* sits in its file: "page 3", "slide 2", "sheet Sales".

    Empty when the picture has no page number (a photo).

    Examples:
        >>> art = {
        ...     "meta": {
        ...         "segments": [
        ...             {
        ...                 "kind": "sheet",
        ...                 "label": "Sales",
        ...                 "start": 0,
        ...                 "end": 1,
        ...                 "page": 2,
        ...             }
        ...         ]
        ...     }
        ... }
        >>> page_label({"page": 2}, art)
        'sheet Sales'
        >>> page_label({"page": 4}, {"meta": {"kind": "slides"}})
        'slide 4'
        >>> page_label({"page": 1}, {"meta": {}}), page_label({}, {"meta": {}})
        ('page 1', '')
    """
    page = image.get("page")
    if not isinstance(page, int) or isinstance(page, bool):
        return ""
    meta = artifact.get("meta") or {}
    segment = next(
        (s for s in meta.get("segments") or [] if s.get("page") == page), None
    )
    kind = (segment or {}).get("kind") or (
        "slide" if meta.get("kind") == "slides" else "page"
    )
    if kind == "sheet":
        name = (segment or {}).get("label")
        return f"sheet {name}" if name else f"sheet {page}"
    if kind == "slide":
        return f"slide {page}"
    return f"page {page}"


def fill(template: str, *, name: str, page: str) -> str:
    """The label text: *template* with ``{name}`` and ``{page}`` filled in.

    A separator next to an empty value is dropped, so a photo labelled
    with the name template shows just its name.

    Examples:
        >>> fill("{name} · {page}", name="q3.pdf", page="page 2")
        'q3.pdf · page 2'
        >>> fill("{name} · {page}", name="cat.jpg", page="")
        'cat.jpg'
        >>> fill("Draft — {page}", name="x", page="")
        'Draft'
        >>> fill("{other} stays", name="x", page="")
        '{other} stays'
        >>> fill("Draft -", name="x", page="")
        'Draft -'
    """
    text = template.replace("{name}", name).replace("{page}", page)
    emptied = ("{name}" in template and not name) or ("{page}" in template and not page)
    if emptied:
        text = text.strip().strip("·—-|,:").strip()
    return text.strip()


def _font(size: int) -> Any:
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1, FreeType
    except (TypeError, OSError):  # pragma: no cover - old Pillow / no FreeType
        return ImageFont.load_default()


def _fit(draw: Any, text: str, font: Any, width: float) -> str:
    """*text*, shortened in the middle with "…" until it fits *width* px."""
    if draw.textlength(text, font=font) <= width:
        return text
    keep = len(text)
    while keep > 1:
        keep -= 1
        head = text[: (keep + 1) // 2]
        tail = text[len(text) - keep // 2 :] if keep // 2 else ""
        candidate = f"{head}…{tail}"
        if draw.textlength(candidate, font=font) <= width:
            return candidate
    return "…"


def label_picture(data: bytes, mimetype: str, text: str) -> tuple[bytes, str]:
    """Return *data* with *text* in a strip above it: ``(bytes, mimetype)``.

    JPEG stays JPEG; every other format becomes PNG. The colour profile is
    kept; other metadata is not (the labelled picture is a new picture).

    Examples:
        >>> from PIL import Image
        >>> buf = io.BytesIO()
        >>> Image.new("RGB", (800, 600), "steelblue").save(buf, "PNG")
        >>> out, kind = label_picture(buf.getvalue(), "image/png", "page 1")
        >>> kind, Image.open(io.BytesIO(out)).size
        ('image/png', (800, 600))
        >>> Image.open(io.BytesIO(out)).getpixel((400, 2))  # the strip
        (255, 255, 255)
    """
    from PIL import Image, ImageDraw

    from ._processors._imageout import pil_encode

    with Image.open(io.BytesIO(data)) as opened:
        opened.load()
        icc = opened.info.get("icc_profile")
        img = opened.copy()

    jpeg = mimetype == "image/jpeg"
    has_alpha = "A" in img.getbands() or "transparency" in img.info
    if img.mode == "L":
        mode, paper, ink, rule = "L", 255, 34, 200
    else:
        mode = "RGBA" if has_alpha and not jpeg else "RGB"
        paper, ink, rule = (*_PAPER, 255) if mode == "RGBA" else _PAPER, _INK, _RULE
    img = img.convert(mode)

    width, height = img.size
    size = max(12, min(64, round(min(width, height) / 40)))
    pad = max(3, size // 3)
    strip = size + 2 * pad
    if height >= 4 * strip:
        # Same canvas: the content shrinks to make room (max_dim stays true).
        canvas_h = height
        scale = (height - strip) / height
        content = img.resize(
            (max(1, round(width * scale)), height - strip), Image.Resampling.LANCZOS
        )
    else:
        # Too small to share its height: the canvas grows by the strip.
        canvas_h = height + strip
        content = img
    canvas = Image.new(mode, (width, canvas_h), paper)
    canvas.paste(content, ((width - content.width) // 2, strip))

    draw = ImageDraw.Draw(canvas)
    font = _font(size)
    shown = _fit(draw, text, font, width - 2 * pad)
    draw.text((pad, strip / 2), shown, font=font, fill=ink, anchor="lm")
    draw.line([(0, strip - 1), (width, strip - 1)], fill=rule, width=1)

    pillow_format = "JPEG" if jpeg else "PNG"
    out = _encode(canvas, pillow_format, pil_encode, icc)
    return out, "image/jpeg" if jpeg else "image/png"


def _encode(img: Any, pillow_format: str, pil_encode: Any, icc: bytes | None) -> bytes:
    if not icc:
        return pil_encode(img, pillow_format)
    # pil_encode has no profile argument; save directly with the same settings.
    from ._processors._imageout import DEFAULT_QUALITY

    buf = io.BytesIO()
    kwargs: dict[str, Any] = {"icc_profile": icc}
    if pillow_format == "JPEG":
        kwargs.update(quality=DEFAULT_QUALITY, optimize=True)
    img.save(buf, format=pillow_format, **kwargs)
    return buf.getvalue()


def _renamed(name: str, mimetype: str) -> str:
    """*name* with the extension of *mimetype* (a GIF labelled is a PNG).

    Examples:
        >>> _renamed("anim.gif", "image/png"), _renamed("p-1.jpg", "image/jpeg")
        ('anim.png', 'p-1.jpg')
    """
    stem, ext = os.path.splitext(name)
    wanted = ".jpg" if mimetype == "image/jpeg" else ".png"
    if ext.lower() in ({".jpg", ".jpeg"} if wanted == ".jpg" else {".png"}):
        return name
    return f"{stem or name}{wanted}"


def apply_watermark(
    artifact: dict,
    value: Any,
    *,
    source: str,
    hint: str | None = None,
) -> dict:
    """Label every picture of *artifact* as ``watermark: value`` asks.

    Never raises. What could not be done is said in ``meta.warnings``:
    no pictures (with *hint*, how to ask for them), pictures with no page
    for a ``page`` label, Pillow missing, a picture that could not be read.
    A failed artifact is returned unchanged.

    Args:
        artifact: The processor's result (changed in place and returned).
        value: The ``watermark`` option value.
        source: The file's name or address, for ``{name}``.
        hint: How this format makes pictures on request (``"images: true"``),
            named when there are none.

    Examples:
        >>> from attachments.types import make_artifact
        >>> a = apply_watermark(
        ...     make_artifact(text="hi"), "page", source="a.pdf", hint="images: true"
        ... )
        >>> a["meta"]["warnings"]
        ['watermark: a.pdf has no pictures to label — ask for them with images: true']
    """
    value, legacy = split_legacy(value)
    template = template_for(value)
    meta = artifact.setdefault("meta", {})
    if template is None or meta.get("error"):
        return artifact
    warnings: list[str] = []
    if legacy:
        warnings.append(
            "watermark: position and style are gone; the label always goes "
            f"in a strip above the picture (drawn: {value!r})"
        )
    images = artifact.get("images") or []
    name = display_name(source)
    if not images:
        message = f"watermark: {name} has no pictures to label"
        if hint:
            message += f" — ask for them with {hint}"
        warnings.append(message)
    else:
        try:
            import PIL  # noqa: F401
        except ImportError:
            warnings.append(
                "watermark needs Pillow — install with: pip install attachments[image]"
            )
            images = []
    unlabelled = failed = 0
    for image in images:
        raw = image.get("bytes")
        if not isinstance(raw, bytes | bytearray):
            continue
        text = fill(template, name=name, page=page_label(image, artifact))
        if not text:
            unlabelled += 1
            continue
        try:
            labelled, mimetype = label_picture(
                bytes(raw), image.get("mimetype") or "", text
            )
        except Exception:
            failed += 1
            continue
        image["bytes"] = labelled
        image["name"] = _renamed(image.get("name") or "image", mimetype)
        image["mimetype"] = mimetype
    if unlabelled:
        warnings.append(
            f"watermark: {unlabelled} picture(s) of {name} have no page to show "
            "— use watermark: name, or your own text"
        )
    if failed:
        warnings.append(f"watermark: {failed} picture(s) of {name} could not be read")
    if len(images) > unlabelled + failed:
        meta.setdefault("extra", {})["watermark"] = template
    if warnings:
        from ._options import warn_option

        meta.setdefault("warnings", []).extend(warnings)
        for warning in warnings:
            warn_option(warning)
    return artifact
