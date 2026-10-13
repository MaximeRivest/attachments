"""Processor for raster images (.png, .jpg, .jpeg, .gif, .webp, .bmp, .tiff, .heic).

Identifies the image with Pillow and emits a single ImageItem. Web-friendly
formats (png/jpeg/gif/webp) pass through untouched; exotic formats (bmp,
tiff, heic, ...) are re-encoded to PNG; an optional ``max_dim`` downscales
the longest side while preserving the aspect ratio, and an optional
``rotate`` turns the image clockwise (applied before ``max_dim``).

Photos are delivered upright: a camera's EXIF orientation tag ("this photo
is sideways, turn it when showing") is applied to the pixels, because
models and APIs do not reliably read the tag, and OCR cannot read sideways
text. ``rotate`` then turns the image as you see it.

Requires Pillow: ``pip install attachments[image]``
HEIC/HEIF additionally requires pillow-heif: ``pip install attachments[heic]``
"""

from __future__ import annotations

import io
from typing import Any

from .._options import Option, register_options
from .._watermark import WATERMARK
from ..types import (
    ERROR_INVALID_OPTION,
    ERROR_PARSE,
    ERROR_PROCESSING,
    error_artifact,
    make_artifact,
    missing_dep_artifact,
)
from . import register_processor
from ._imageout import check_image_output, limit, output_format, pil_encode
from ._metadata import strip_metadata

#: Formats served as-is (original bytes + mimetype) when no resize is needed.
_PASSTHROUGH = {
    "PNG": ("image/png", "png"),
    "JPEG": ("image/jpeg", "jpg"),
    "GIF": ("image/gif", "gif"),
    "WEBP": ("image/webp", "webp"),
}


#: Hint stored in meta.extra when OCR could help but rapidocr is missing.
#: Local remedy first, free hosted tier second (ocr is a HEAVY install).
OCR_HINT = (
    "Image with text? pip install attachments[ocr], "
    "or the free hosted tier: attachments.dev"
)

#: OCR engines accepted by the ``ocr_engine`` option.
OCR_ENGINES = ("rapidocr", "lighton")

#: Environment variables configuring the LightOn OCR engine (see _lighton).
LIGHTON_URL_ENV = "ATTACHMENTS_LIGHTON_URL"
LIGHTON_MODEL_ENV = "ATTACHMENTS_LIGHTON_MODEL"

#: Error message when ocr_engine=lighton is requested but no endpoint is set.
LIGHTON_URL_UNSET_MSG = (
    "ocr_engine=lighton requires the ATTACHMENTS_LIGHTON_URL environment "
    "variable (e.g. http://127.0.0.1:8830/v1, or unix:/path/to/vllm.sock) "
    "pointing at an OpenAI-compatible vLLM endpoint serving LightOnOCR. This "
    "engine is a SERVER capability — it is not a local pip install; deploy "
    "the model with vLLM and set the env var on the machine running "
    "attachments."
)


def resolve_engine(ocr_engine: str | None) -> tuple[str, bool]:
    """``(engine, asked)``: the OCR engine to use, and whether the caller named it.

    Unnamed, it is the configured one (``configure(ocr_engine=...)`` or
    ``ATTACHMENTS_OCR_ENGINE``; a server sets it), else ``"rapidocr"``.

    Examples:
        >>> resolve_engine("LightOn")
        ('lighton', True)
        >>> from attachments.config import reset_config
        >>> reset_config()
        >>> resolve_engine(None)
        ('rapidocr', False)
    """
    if ocr_engine:
        return str(ocr_engine).lower(), True
    from ..config import get_config

    return str(get_config("ocr_engine") or "rapidocr").lower(), False


def _ocr_input(img: Any) -> Any:
    """*img* as RGB for OCR; transparency flattened onto white.

    Converting a transparent image straight to RGB turns the transparent
    pixels black, which hides dark text drawn on them.
    """
    from PIL import Image

    if img.mode in ("RGBA", "LA", "PA") or (
        img.mode == "P" and "transparency" in img.info
    ):
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return img if img.mode == "RGB" else img.convert("RGB")


def _looks_heic(data: bytes, filename: str | None) -> bool:
    """Cheap HEIC/HEIF detection: extension or ISO-BMFF ftyp brand sniff."""
    if filename and filename.lower().rsplit(".", 1)[-1] in ("heic", "heif"):
        return True
    return data[4:8] == b"ftyp" and data[8:12].startswith((b"hei", b"mif1", b"msf1"))


def _exif_orientation(img: Any) -> int | None:
    """EXIF orientation tag (1-8), or ``None`` when absent or unreadable."""
    try:
        value = img.getexif().get(0x0112)
    except Exception:  # malformed EXIF must not fail the image
        return None
    return value if isinstance(value, int) and 1 <= value <= 8 else None


def image_processor(
    data: bytes,
    *,
    filename: str | None = None,
    max_dim: int | None = None,
    rotate: int | None = None,
    image_format: str | None = None,
    quality: int | None = None,
    ocr: bool | str = False,
    ocr_engine: str | None = None,
    metadata: bool = False,
    **_: Any,
) -> dict[str, Any]:
    """Convert image bytes to an artifact carrying one ImageItem.

    Options:
        filename: Original filename (used for metadata and the image name).
        max_dim: Downscale so the longest side is at most this many pixels
            (``None`` or ``0``: no limit).
        rotate: Rotate clockwise by this many degrees, as the image is seen
            (after its EXIF orientation); negative values rotate
            counterclockwise. Normalized modulo 360; applied before
            ``max_dim``. The canvas grows, so non-right angles get
            background fill in the corners.
        image_format: ``"png"`` or ``"jpeg"`` to choose the output format.
            Default ``None``: keep JPEG as JPEG and web formats as they
            are; exotic formats become PNG. JPEG output of a transparent
            image is flattened onto white.
        quality: JPEG quality, 1-95 (default 85 when encoding JPEG).
            Given explicitly, it re-encodes a JPEG even when nothing else
            changes (to make it smaller).
        ocr: ``True`` runs RapidOCR and the recognized text becomes the
            artifact text (``extra.ocr = True``); missing rapidocr yields the
            typed missing-dependency artifact. ``"auto"`` behaves like
            ``True`` only when rapidocr is installed, otherwise it is a
            no-op that records ``extra.ocr_hint``. ``False`` (default)
            never runs OCR.
        metadata: ``False`` (default) removes what the file says about its
            owner: GPS location, dates, camera serial, thumbnails (EXIF,
            XMP, IPTC), without touching the pixels; the kinds removed are
            in ``extra.metadata_removed``. ``True`` keeps the file's bytes.
        ocr_engine: ``"rapidocr"`` (local) or ``"lighton"`` — a LightOnOCR
            vLLM endpoint set by ``ATTACHMENTS_LIGHTON_URL`` (a server
            capability, not a pip install; see ``_lighton``). Default: the
            configured engine (``ATTACHMENTS_OCR_ENGINE``), else rapidocr.
            Without an endpoint: rapidocr (``extra.ocr_engine_fallback``),
            except an explicit ``lighton`` with forced OCR, an
            ``invalid-option`` error. When the endpoint fails, RapidOCR
            reads the image if installed (a warning says so).

    Behavior:
        - png/jpeg/gif/webp with nothing to change: bytes pass through.
        - ``max_dim`` exceeded, nonzero ``rotate``, another ``image_format``,
          or an explicit ``quality`` for JPEG output: transform and
          re-encode — in ``image_format`` when given, else JPEG (quality
          85) when the original was JPEG, PNG otherwise.
        - Exotic formats (bmp/tiff/heic/...): re-encode (PNG by default).
        - OCR reads the full-size, lossless image, not a shrunk or JPEG copy.

    Never raises: corrupt bytes yield a ``parse-error`` artifact and a
    missing Pillow (or pillow-heif for HEIC inputs) yields the typed
    ``missing-dependency`` artifact.
    """
    source = filename or "image"

    invalid = check_image_output(
        max_dim=max_dim, image_format=image_format, quality=quality
    )
    if invalid:
        artifact = error_artifact(source, ERROR_INVALID_OPTION, invalid)
        artifact["meta"]["kind"] = "image"
        return artifact

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
        # EXIF orientation 2-8: the pixels are stored turned or mirrored.
        orientation = _exif_orientation(img)
        if orientation not in (None, 1):
            from PIL import ImageOps

            img = ImageOps.exif_transpose(img)

        degrees = 0 if rotate is None else int(rotate) % 360
        if degrees:
            # Clockwise, like CSS, ImageMagick and 0.25 (PIL's own rotate is
            # counterclockwise); expand=True grows the canvas so nothing is
            # cropped (non-right angles get corner fill).
            img = img.rotate(-degrees, expand=True)

        cap = limit(max_dim)
        resized = cap is not None and max(img.size) > cap
        if image_format is not None:
            out_format, mimetype, ext = output_format(image_format)
        elif original_format == "JPEG":
            out_format, mimetype, ext = output_format("jpeg")
        else:
            out_format, mimetype, ext = output_format("png")
        reencode = (
            resized
            or bool(degrees)
            or orientation not in (None, 1)
            or original_format not in _PASSTHROUGH
            or (image_format is not None and out_format != original_format)
            or (quality is not None and out_format == "JPEG")
        )

        # OCR wants the full-size, lossless image: keep it when the
        # delivered copy is shrunk or lossy (see the OCR block below).
        ocr_source: Any = None
        if not reencode:
            mimetype, ext = _PASSTHROUGH[original_format]
            name = filename or f"image.{ext}"
            image_bytes = data
        else:
            if resized or out_format == "JPEG":
                ocr_source = img.copy() if resized else img
            if resized:
                img.thumbnail((cap, cap))  # in-place, preserves aspect
            image_bytes = pil_encode(img, out_format, quality)
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
        if orientation not in (None, 1):
            extra["exif_orientation"] = orientation  # applied: now upright

        text = ""
        ocr_warnings: list[str] = []
        if ocr is True or str(ocr).lower() == "always" or str(ocr).lower() == "auto":
            # The full-size picture, before any shrinking or JPEG.
            ocr_image = ocr_source if ocr_source is not None else img
            ocr_forced = ocr is True or str(ocr).lower() == "always"
            engine, asked = resolve_engine(ocr_engine)
            if engine not in OCR_ENGINES:
                return error_artifact(
                    source,
                    ERROR_INVALID_OPTION,
                    f"Unknown ocr_engine {ocr_engine!r} "
                    f"(expected one of: {', '.join(OCR_ENGINES)})",
                )
            if engine == "lighton":
                from . import _lighton

                where = _lighton.endpoint()
                if where is None:
                    if ocr_forced and asked:
                        return error_artifact(
                            source, ERROR_INVALID_OPTION, LIGHTON_URL_UNSET_MSG
                        )
                    # no endpoint configured: the local engine
                    engine = "rapidocr"
                    extra["ocr_engine_fallback"] = "rapidocr"
                else:
                    from ..deps import check_dep

                    rapid = None
                    if check_dep("ocr").available:
                        from ._ocr import recognize as rapid
                    reader = _lighton.Reader(where, rapid)
                    try:
                        result = reader(ocr_image)
                    except Exception as e:
                        return error_artifact(
                            source,
                            ERROR_PROCESSING,
                            f"LightOn OCR request failed: {e}. Check that the "
                            f"vLLM endpoint at {LIGHTON_URL_ENV} "
                            f"({where.label}) is running and reachable.",
                        )
                    text = result.text
                    extra["ocr"] = True
                    extra["ocr_model"] = reader.model
                    if reader.fell_back:
                        extra["ocr_backend"] = "rapidocr"
                        extra["ocr_engine_fallback"] = "rapidocr"
                        ocr_warnings.append(reader.warning())
                        if result.turned:
                            extra["ocr_turned"] = result.turned
                    else:
                        extra["ocr_backend"] = "lighton"
            if engine == "rapidocr":
                from ..deps import check_dep

                if check_dep("ocr").available:
                    from ._ocr import recognize

                    result = recognize(_ocr_input(ocr_image))
                    text = result.text
                    extra["ocr"] = True
                    extra["ocr_backend"] = "rapidocr"
                    if result.turned:
                        extra["ocr_turned"] = result.turned
                elif ocr_forced:
                    # Forced OCR without rapidocr is a typed missing-dependency.
                    return missing_dep_artifact(source, "ocr")
                else:
                    extra["ocr_hint"] = OCR_HINT

        if not metadata:
            image_bytes, removed = strip_metadata(image_bytes, mimetype)
            if removed:
                extra["metadata_removed"] = removed
        return make_artifact(
            text=text,
            images=[{"name": name, "mimetype": mimetype, "bytes": image_bytes}],
            meta={
                "kind": "image",
                "extra": extra,
                **({"warnings": ocr_warnings} if ocr_warnings else {}),
            },
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
        help="Downscale so the longest side is at most this many pixels (0 = no limit)",
        example="max_dim: 1024",
    ),
    Option(
        name="rotate",
        type="int",
        help="Rotate clockwise by this many degrees (negative = counterclockwise)",
        example="rotate: 90",
    ),
    Option(
        name="image_format",
        type="str",
        help="Output format: png or jpeg (default: keep jpeg, other formats png)",
        example="image_format: jpeg",
    ),
    Option(
        name="quality",
        type="int",
        help="JPEG quality, 1-95 (default 85 when encoding jpeg)",
        example="quality: 75",
    ),
    Option(
        name="metadata",
        type="bool",
        default=False,
        help=(
            "Keep the photo's metadata (GPS location, dates, camera); "
            "removed by default, pixels untouched"
        ),
        example="metadata: true",
    ),
    Option(
        name="ocr",
        type="bool_or_auto",
        default=False,
        help=(
            "Recognize text in the image with RapidOCR: true/false, or auto "
            "(only when rapidocr is installed)"
        ),
        example="ocr: true",
    ),
    Option(
        name="ocr_engine",
        type="str",
        default="rapidocr",
        help=(
            "OCR engine: rapidocr (local, default) or lighton (LightOnOCR, "
            "a server's vLLM endpoint via ATTACHMENTS_LIGHTON_URL; a server "
            "may make it its default with ATTACHMENTS_OCR_ENGINE)"
        ),
        example="ocr_engine: lighton",
    ),
    WATERMARK,
)


def register() -> None:
    """Register the image processor and its option schema (idempotent)."""
    for ext in EXTENSIONS:
        register_processor(ext, image_processor)
        register_options(ext, OPTIONS)


register()
