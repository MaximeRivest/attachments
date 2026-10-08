"""Type definitions and artifact helpers for the attachments library.

This module implements the frozen IR contract (see ``spec/IR-CONTRACT.md``):
every processor returns an :class:`Artifact`-shaped dict with a typed
``meta`` envelope, and failures are expressed as machine-readable error
codes — never as free-form strings that consumers must pattern-match.

Helper API:

* :func:`make_artifact` — build an artifact with safe defaults.
* :func:`error_artifact` — build a failed artifact with a typed error code.
* :func:`missing_dep_artifact` — typed missing-dependency signal (drives
  the local-to-service fallback in ``core.py``).
* :func:`is_missing_dependency` — the ONLY sanctioned way for routing code
  to detect a missing-dependency result.
* :func:`normalize_artifact` — fill required keys and ``meta.source``.
* :func:`artifact_to_wire` / :func:`artifact_from_wire` — the JSON wire
  form (images as ``bytes_b64``) and back.
* :class:`AttachmentsError` — raised by ``Artifacts.raise_for_errors()``.

Example::

    from attachments.types import Artifact, make_artifact


    def my_processor(data: bytes, **opts) -> Artifact:
        return make_artifact(text=data.decode(), meta={"kind": "custom"})
"""

from __future__ import annotations

import base64
import binascii
import copy
from typing import Any, NotRequired, Protocol, TypedDict

# ---------------------------------------------------------------------------
# Error codes (spec/IR-CONTRACT.md — frozen, do not rename)
# ---------------------------------------------------------------------------

#: Optional dependency not installed — DRIVES SERVICE FALLBACK.
ERROR_MISSING_DEPENDENCY = "missing-dependency"
#: Encrypted file with a wrong or missing password.
ERROR_PASSWORD_REQUIRED = "password-required"
#: File exists but could not be parsed.
ERROR_PARSE = "parse-error"
#: Source could not be resolved/fetched.
ERROR_UNPACK = "unpack-error"
#: Remote service failed.
ERROR_SERVICE = "service-error"
#: Option value invalid for this processor.
ERROR_INVALID_OPTION = "invalid-option"
#: Anything else.
ERROR_PROCESSING = "processing-error"

#: Features whose local install is genuinely heavy (onnxruntime, whisper).
#: ONLY these missing-dependency messages mention the free hosted tier —
#: light extras (pdf, xlsx, ...) keep the plain pip install remedy.
HEAVY_FEATURES = frozenset({"ocr", "audio"})

#: Extra sentence appended for HEAVY_FEATURES missing-dependency messages.
_HOSTED_TIER_HINT = (
    "Or use the free hosted tier: configure(service_url="
    '"https://api.attachments.dev/v1") - details at attachments.dev.'
)


class ErrorInfo(TypedDict):
    """Typed error payload stored at ``meta["error"]``.

    Keys
    ----
    code : str
        One of the ``ERROR_*`` constants in this module.
    message : str
        Human-readable description, including a remedy when known
        (missing-dependency messages always include the pip install hint).
    """

    code: str
    message: str


class Segment(TypedDict):
    """Structural segment of an artifact's text (page/sheet/slide/section).

    ``start``/``end`` are offsets into ``artifact["text"]``
    (inclusive/exclusive). ``page`` (optional, 1-based) is the page or
    slide number the segment comes from; it is the same number images
    carry in ``ImageItem.page``, which is how consumers place each image
    next to its page's text. ``label`` is for people and is never parsed.
    """

    kind: str
    label: str
    start: int
    end: int
    page: NotRequired[int]


class Meta(TypedDict, total=False):
    """Typed metadata envelope for an :class:`Artifact`.

    All keys are optional and ABSENT when not applicable (never ``None``).
    ``source`` is required after normalization — ``core.py`` sets it.

    Keys
    ----
    source : str
        Original filename / path (set by :func:`normalize_artifact`).
    kind : str
        Format hint: ``"text"``, ``"pdf"``, ``"table"``, ``"document"``,
        ``"html"``, ``"slides"``, ``"image"``, ...
    via : str
        ``"service"`` when processed remotely (absent = local).
    error : ErrorInfo
        Present only on failure.
    note : str
        Informational message (e.g. ``"no processor available"``).
    warnings : list[str]
        Non-fatal warnings (e.g. DSL unknown-option warnings).
    segments : list[Segment]
        Structural segmentation (pages/sheets/slides) with text offsets.
    extra : dict
        Processor-specific freeform metadata (backends, counts, ...).
    """

    source: str
    kind: str
    via: str
    error: ErrorInfo
    note: str
    warnings: list[str]
    segments: list[Segment]
    extra: dict[str, Any]


class ImageItem(TypedDict, total=False):
    """A single image extracted from a document.

    Required keys: ``name``, ``mimetype``, ``bytes`` (in-process).
    Optional keys: ``page``, ``bytes_b64`` (JSON wire transport only —
    never both ``bytes`` and ``bytes_b64`` on output).
    """

    name: str
    mimetype: str
    bytes: bytes
    page: int
    bytes_b64: str  # present only during JSON serialisation


class Artifact(TypedDict):
    """Universal output format returned by every processor and by ``att()``.

    Keys
    ----
    text : str
        Extracted text content (may be empty on error).
    images : list[ImageItem]
        Images extracted from the source (e.g. rendered PDF pages).
    audio : list[dict[str, Any]]
        Reserved for future audio extraction.
    video : list[dict[str, Any]]
        Reserved for future video extraction.
    meta : Meta
        Typed metadata envelope (source, kind, error, ...).
    """

    text: str
    images: list[ImageItem]
    audio: list[dict[str, Any]]
    video: list[dict[str, Any]]
    meta: Meta


class Processor(Protocol):
    """The processor contract, as frozen in ``spec/IR-CONTRACT.md``.

    A processor is a pure function
    ``(data: bytes, *, filename=None, **options) -> Artifact``. The core
    pipeline always calls it as ``proc(data, filename=filename, **options)``,
    so implementations must accept ``filename`` (a ``**options`` catch-all
    is enough) and never raise: missing optional dependencies become
    :func:`missing_dep_artifact`, bad input becomes :func:`error_artifact`.

    Example::

        def my_processor(data: bytes, **options) -> Artifact:
            return make_artifact(text=data.decode(errors="replace"))
    """

    def __call__(
        self,
        data: bytes,
        /,
        *,
        filename: str | None = None,
        **options: Any,
    ) -> Artifact: ...


def make_artifact(
    *,
    text: str = "",
    images: list[ImageItem] | None = None,
    audio: list[dict[str, Any]] | None = None,
    video: list[dict[str, Any]] | None = None,
    meta: Meta | None = None,
) -> Artifact:
    """Create an :class:`Artifact` dict with safe defaults.

    This is the recommended way for processors to build their return value.

    Examples:
        >>> a = make_artifact(text="hello", meta={"kind": "text"})
        >>> a["text"]
        'hello'
        >>> a["images"]
        []
        >>> a["meta"]["kind"]
        'text'
        >>> make_artifact()["meta"]
        {}
    """
    return {
        "text": text,
        "images": images if images is not None else [],
        "audio": audio if audio is not None else [],
        "video": video if video is not None else [],
        "meta": meta if meta is not None else {},
    }


def error_artifact(source: str, code: str, message: str) -> Artifact:
    """Create a failed artifact carrying a typed ``meta.error``.

    Args:
        source: Filename / path / input spec that failed.
        code: One of the ``ERROR_*`` constants in this module.
        message: Human-readable description (include a remedy when known).

    Examples:
        >>> a = error_artifact("broken.pdf", ERROR_PARSE, "not a PDF")
        >>> a["text"]
        ''
        >>> a["meta"]["source"]
        'broken.pdf'
        >>> a["meta"]["error"]["code"]
        'parse-error'
        >>> a["meta"]["error"]["message"]
        'not a PDF'
    """
    return make_artifact(
        meta={"source": source, "error": {"code": code, "message": message}}
    )


def missing_dep_artifact(source: str, feature: str) -> Artifact:
    """Create the typed missing-dependency artifact for *feature*.

    The install hint is looked up from ``deps.DEPENDENCY_MAP`` so the
    error message always tells users how to fix the problem. Core routing
    uses :func:`is_missing_dependency` on this artifact to decide whether
    to fall back to the service.

    The local remedy always comes first. Only for :data:`HEAVY_FEATURES`
    (``ocr``, ``audio`` — onnxruntime/whisper installs are genuinely heavy)
    does the message ALSO mention the free hosted tier; light extras keep
    the plain pip install message.

    Args:
        source: Filename / path being processed.
        feature: Feature name from ``deps.DEPENDENCY_MAP``
            (e.g. ``"pdf"``, ``"xlsx"``, ``"docx"``, ``"html"``).

    Examples:
        >>> a = missing_dep_artifact("report.docx", "docx")
        >>> a["meta"]["error"]["code"]
        'missing-dependency'
        >>> "pip install" in a["meta"]["error"]["message"]
        True
        >>> "attachments.dev" in a["meta"]["error"]["message"]  # light: no ad
        False
        >>> is_missing_dependency(a)
        True

        >>> heavy = missing_dep_artifact("scan.pdf", "ocr")
        >>> "pip install" in heavy["meta"]["error"]["message"]
        True
        >>> "attachments.dev" in heavy["meta"]["error"]["message"]
        True
    """
    # Imported lazily to avoid import cycles (deps is dependency-free).
    from .deps import DEPENDENCY_MAP, check_dep

    if feature in DEPENDENCY_MAP:
        status = check_dep(feature)
        if not status.install_hint.startswith("pip "):
            # A program, not a Python package (LibreOffice).
            message = f"Processing {source!r} needs {feature}: {status.install_hint}"
            return error_artifact(source, ERROR_MISSING_DEPENDENCY, message)
        missing = f" (missing: {', '.join(status.missing)})" if status.missing else ""
        message = (
            f"Processing {source!r} requires optional dependencies "
            f"for {feature!r}{missing}. Install with: {status.install_hint}"
        )
    else:
        message = (
            f"Processing {source!r} requires optional dependencies "
            f"for {feature!r}. Install with: pip install attachments[{feature}]"
        )
    if feature in HEAVY_FEATURES:
        message = f"{message} {_HOSTED_TIER_HINT}"
    return error_artifact(source, ERROR_MISSING_DEPENDENCY, message)


def is_missing_dependency(artifact: dict) -> bool:
    """Typed check for the missing-dependency error code.

    This is the ONLY way core routing may decide to fall back to the
    service — string-matching error messages is forbidden by the IR
    contract.

    Examples:
        >>> is_missing_dependency(missing_dep_artifact("f.pdf", "pdf"))
        True
        >>> is_missing_dependency(error_artifact("f.pdf", ERROR_PARSE, "bad"))
        False
        >>> is_missing_dependency(make_artifact(text="fine"))
        False
        >>> is_missing_dependency({})
        False
    """
    error = artifact.get("meta", {}).get("error")
    if not isinstance(error, dict):
        return False
    return error.get("code") == ERROR_MISSING_DEPENDENCY


def normalize_artifact(artifact: dict, source: str) -> Artifact:
    """Ensure *artifact* has all required keys; set ``meta.source`` if absent.

    Mutates and returns the same dict for convenience.

    Examples:
        >>> result = normalize_artifact({"text": "hello"}, "test.txt")
        >>> result["text"]
        'hello'
        >>> result["images"]
        []
        >>> result["meta"]["source"]
        'test.txt'

        >>> # Preserves existing values
        >>> result = normalize_artifact(
        ...     {"text": "hi", "meta": {"kind": "text"}}, "f.txt"
        ... )
        >>> result["meta"]["kind"]
        'text'
        >>> result["meta"]["source"]
        'f.txt'
    """
    artifact.setdefault("text", "")
    artifact.setdefault("images", [])
    artifact.setdefault("audio", [])
    artifact.setdefault("video", [])
    artifact.setdefault("meta", {})
    artifact["meta"].setdefault("source", source)
    return artifact  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Wire form (spec/IR-CONTRACT.md, "Wire format")
# ---------------------------------------------------------------------------


def _image_to_wire(image: dict) -> dict:
    """Return a wire copy of one ImageItem: raw ``bytes`` -> ``bytes_b64``.

    Key order is preserved (``bytes_b64`` takes the place of ``bytes``).
    When both keys are present, in-process ``bytes`` win.
    """
    raw = image.get("bytes")
    out: dict[str, Any] = {}
    for key, value in image.items():
        if key == "bytes_b64" and raw is not None:
            continue
        if key == "bytes":
            if not isinstance(value, bytes | bytearray | memoryview):
                raise TypeError(
                    f"image {image.get('name')!r}: 'bytes' must be bytes, "
                    f"got {type(value).__name__}"
                )
            out["bytes_b64"] = base64.b64encode(bytes(value)).decode("ascii")
        else:
            out[key] = copy.deepcopy(value)
    return out


def artifact_to_wire(artifact: dict) -> dict:
    """Return the JSON wire form of *artifact*: a new dict, input untouched.

    Each image's raw ``bytes`` become standard base64 in ``bytes_b64``;
    everything else is deep-copied as-is. The result is what the server
    sends, what ``json.dumps`` accepts, and what
    ``spec/artifact.schema.json`` validates.

    Examples:
        >>> art = make_artifact(
        ...     images=[{"name": "p.png", "mimetype": "image/png", "bytes": b"hi"}],
        ...     meta={"source": "p.pdf"},
        ... )
        >>> wire = artifact_to_wire(art)
        >>> wire["images"][0]
        {'name': 'p.png', 'mimetype': 'image/png', 'bytes_b64': 'aGk='}
        >>> art["images"][0]["bytes"]  # the original keeps its bytes
        b'hi'
        >>> artifact_from_wire(wire) == art
        True
    """
    out: dict[str, Any] = {}
    for key, value in artifact.items():
        if key == "images":
            out[key] = [_image_to_wire(image) for image in value or []]
        else:
            out[key] = copy.deepcopy(value)
    return out


def artifact_from_wire(data: dict) -> Artifact:
    """Rebuild an in-process artifact from its JSON wire form.

    The inverse of :func:`artifact_to_wire`: returns a new dict whose
    images carry raw ``bytes`` again (``bytes_b64`` removed). Data that
    was saved to disk or received over the network is checked, and bad
    data fails loudly instead of losing an image quietly:

    * ``ValueError`` when an image's ``bytes_b64`` is not valid base64,
      or when ``text``/``images``/``meta`` have the wrong type.
    * ``TypeError`` when *data* is not a dict.

    Missing ``text``/``images``/``audio``/``video``/``meta`` are filled with
    empty values; ``meta.source`` is never invented (a caller that knows
    the file name sets it, as ``att()`` does). This is a structural check,
    not full JSON Schema validation (that would need a dependency;
    ``spec/artifact.schema.json`` is the reference).

    Examples:
        >>> art = artifact_from_wire(
        ...     {
        ...         "text": "",
        ...         "images": [
        ...             {"name": "p.png", "mimetype": "image/png", "bytes_b64": "aGk="}
        ...         ],
        ...         "meta": {"source": "p.pdf"},
        ...     }
        ... )
        >>> art["images"][0]["bytes"], art["audio"]
        (b'hi', [])
        >>> artifact_from_wire(
        ...     {
        ...         "images": [{"name": "x.png", "bytes_b64": "%%"}],
        ...         "meta": {"source": "x.png"},
        ...     }
        ... )
        Traceback (most recent call last):
        ...
        ValueError: x.png: image 'x.png' has invalid base64 in 'bytes_b64'
    """
    if not isinstance(data, dict):
        raise TypeError(f"an artifact must be a dict, got {type(data).__name__}")
    out: Any = copy.deepcopy(data)
    meta = out.get("meta", {})
    if not isinstance(meta, dict):
        raise ValueError(f"'meta' must be an object, got {type(meta).__name__}")
    where = meta.get("source") or "(unknown)"
    if not isinstance(out.get("text", ""), str):
        raise ValueError(f"{where}: 'text' must be a string")
    images = out.get("images", [])
    if not isinstance(images, list):
        raise ValueError(f"{where}: 'images' must be a list")
    rebuilt: list[dict] = []
    for image in images:
        if not isinstance(image, dict):
            raise ValueError(f"{where}: each image must be an object")
        name = image.get("name") or "image"
        item: dict[str, Any] = {}
        for key, value in image.items():
            if key != "bytes_b64":
                item[key] = value
                continue
            if "bytes" in image:
                continue  # already in-process; bytes win (see _image_to_wire)
            if not isinstance(value, str):
                raise ValueError(
                    f"{where}: image {name!r} has a non-string 'bytes_b64'"
                )
            try:
                item["bytes"] = base64.b64decode(value, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError(
                    f"{where}: image {name!r} has invalid base64 in 'bytes_b64'"
                ) from exc
        rebuilt.append(item)
    out["images"] = rebuilt
    for key, empty in (("text", ""), ("audio", []), ("video", []), ("meta", {})):
        out.setdefault(key, empty)
    return out


# ---------------------------------------------------------------------------
# Raising on failure (opt-in; att() itself never raises)
# ---------------------------------------------------------------------------


def _format_error_summary(errors: list[dict]) -> str:
    """One readable message for :class:`AttachmentsError`.

    Examples:
        >>> print(
        ...     _format_error_summary(
        ...         [{"source": "a.pdf", "code": "parse-error", "message": "bad"}]
        ...     )
        ... )
        a.pdf: parse-error — bad
        >>> print(
        ...     _format_error_summary(
        ...         [
        ...             {"source": "a.pdf", "code": "parse-error", "message": "bad"},
        ...             {
        ...                 "source": "b.docx",
        ...                 "code": "missing-dependency",
        ...                 "message": "pip",
        ...             },
        ...         ]
        ...     )
        ... )
        2 inputs failed:
          a.pdf: parse-error — bad
          b.docx: missing-dependency — pip
    """
    lines = [f"{e['source']}: {e['code']} — {e['message']}" for e in errors]
    if len(lines) == 1:
        return lines[0]
    return f"{len(lines)} inputs failed:\n" + "\n".join(f"  {line}" for line in lines)


class AttachmentsError(Exception):
    """Raised by ``Artifacts.raise_for_errors()`` when artifacts failed.

    ``att()`` itself never raises (IR contract): failures come back as
    artifacts with ``meta.error``. Call ``raise_for_errors()`` when a
    failure must stop the program. One exception lists every failure.

    Attributes:
        errors: ``[{"source", "code", "message"}, ...]`` — the same dicts
            as ``Artifacts.errors``.
        artifacts: All artifacts of the run, the ones that worked
            included, so a caller can catch the error and keep going.

    Examples:
        >>> err = AttachmentsError(
        ...     [{"source": "a.pdf", "code": "parse-error", "message": "bad"}]
        ... )
        >>> str(err)
        'a.pdf: parse-error — bad'
        >>> err.errors[0]["code"]
        'parse-error'
        >>> import pickle
        >>> pickle.loads(pickle.dumps(err)).errors == err.errors
        True
    """

    def __init__(self, errors: list[dict], artifacts: list[dict] | None = None):
        self.errors = list(errors)
        self.artifacts = artifacts if artifacts is not None else []
        super().__init__(_format_error_summary(self.errors))

    def __reduce__(self):  # keep it picklable (multiprocessing, workers)
        return (type(self), (self.errors, self.artifacts))
