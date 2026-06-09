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

Example::

    from attachments.types import Artifact, make_artifact


    def my_processor(data: bytes, **opts) -> Artifact:
        return make_artifact(text=data.decode(), meta={"kind": "custom"})
"""

from __future__ import annotations

from typing import Any, TypedDict

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
    (inclusive/exclusive).
    """

    kind: str
    label: str
    start: int
    end: int


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
        >>> is_missing_dependency(a)
        True
    """
    # Imported lazily to avoid import cycles (deps is dependency-free).
    from .deps import DEPENDENCY_MAP, check_dep

    if feature in DEPENDENCY_MAP:
        status = check_dep(feature)
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
