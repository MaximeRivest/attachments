"""Core processing pipeline for attachments.

This module provides the main `att()` function that orchestrates:
1. Unpacking input sources into (filename, bytes) pairs
2. Routing each file to the appropriate processor
3. Processing with local deps or service fallback
4. Normalizing output to consistent artifact format
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ._artifacts import Artifacts
from ._options import get_options, resolve_options, source_option_schemas
from ._processors import processors
from ._sources import unpack
from .config import get_api_key, get_prefer
from .dsl import parse_dsl
from .types import (
    ERROR_MISSING_DEPENDENCY,
    ERROR_PROCESSING,
    ERROR_SERVICE,
    ERROR_UNPACK,
    Processor,
    error_artifact,
    is_missing_dependency,
    make_artifact,
    normalize_artifact,
)
from .utils import detect_extension, is_text_bytes

log = logging.getLogger("attachments.core")


def _route_processor(filename: str, data: bytes) -> tuple[Processor | None, str]:
    """Find the appropriate processor (and its registry key) for a file.

    Routing order:
    1. Filename extension lookup in the processor registry.
    2. Magic-byte content sniffing (``utils.detect_extension``) — only
       routes when the sniffed extension has a registered processor.
    3. Text heuristic fallback (``__text__``).

    Returns ``(None, ext)`` if no processor is found (which will trigger
    service fallback). The key is used to look up the declared option
    schema for this processor. Routing is pure: nothing is recorded in
    ``meta`` here.
    """
    ext = os.path.splitext(filename)[1].lower()
    proc = processors.get(ext)
    if proc is not None:
        return proc, ext
    sniffed = detect_extension(data)
    if sniffed is not None:
        proc = processors.get(sniffed)
        if proc is not None:
            return proc, sniffed
    if is_text_bytes(data):
        proc = processors.get("__text__")
        if proc is not None:
            return proc, "__text__"
    return None, ext


def _empty_artifact(source: str, note: str) -> dict:
    """Create an empty artifact with an informational note (not an error).

    Examples:
        >>> artifact = _empty_artifact("test.bin", "no processor available")
        >>> artifact["meta"]["note"]
        'no processor available'
        >>> artifact["text"]
        ''
    """
    return make_artifact(meta={"source": source, "note": note})


def _artifact_from_exception(source: str, exc: Exception, context: str) -> dict:
    """Convert a processor exception into a typed error artifact.

    ImportError means a missing optional dependency; anything else is a
    generic processing error. Missing-dependency messages always include
    the pip install remedy (IR contract).

    Examples:
        >>> a = _artifact_from_exception("f.xyz", ImportError("no mod"), "local")
        >>> a["meta"]["error"]["code"]
        'missing-dependency'
        >>> "pip install" in a["meta"]["error"]["message"]
        True
        >>> a = _artifact_from_exception("f.xyz", ValueError("bad"), "local")
        >>> a["meta"]["error"]["code"]
        'processing-error'
        >>> a["meta"]["error"]["message"]
        'local processing failed: bad'
    """
    if isinstance(exc, ImportError):
        # exc.name is set when the import machinery raised the error;
        # fall back to the bundle extra covering all built-in processors.
        missing = getattr(exc, "name", None)
        remedy = (
            f"pip install {missing}"
            if missing
            else "pip install attachments[all-local]"
        )
        return error_artifact(
            source,
            ERROR_MISSING_DEPENDENCY,
            f"{context} processing failed: {exc}. "
            f"Missing optional dependency — install with: {remedy}",
        )
    return error_artifact(
        source, ERROR_PROCESSING, f"{context} processing failed: {exc}"
    )


def _attach_warnings(artifact: dict, warnings: list[str]) -> dict:
    """Append option-resolution warnings to ``meta.warnings``.

    The list is created only when there is something to report (IR
    contract: optional meta keys are absent, never empty placeholders).

    Examples:
        >>> a = make_artifact(text="ok")
        >>> _attach_warnings(a, [])["meta"]
        {}
        >>> _attach_warnings(a, ["Unknown option 'x' for .pdf"])["meta"]["warnings"]
        ["Unknown option 'x' for .pdf"]
    """
    if warnings:
        meta = artifact.setdefault("meta", {})
        meta.setdefault("warnings", []).extend(warnings)
    return artifact


def _option_context(filename: str, proc_key: str) -> str:
    """Human-readable owner name for option warnings.

    Examples:
        >>> _option_context("report.pdf", ".pdf")
        '.pdf'
        >>> _option_context("LICENSE", "__text__")
        'text'
    """
    ext = os.path.splitext(filename)[1].lower()
    if ext:
        return ext
    return "text" if proc_key == "__text__" else proc_key


def _process_single(
    filename: str,
    data: bytes,
    *,
    options: dict[str, Any] | None = None,
    api_key: str | None = None,
    prefer: str | None = None,
) -> dict:
    """Process a single file with local/service fallback logic.

    Local processor calls receive options resolved against the processor's
    declared schema (``attachments._options``); resolution warnings are
    attached to the resulting artifact's ``meta.warnings``. Service calls
    receive the RAW options — the service resolves them server-side.

    Options travel as a plain dict (never ``**kwargs``) so that option keys
    like ``filename`` or ``prefer`` can never collide with this function's
    own parameters — unknown keys must become ``meta.warnings``, not
    ``TypeError``.

    Args:
        filename: Name of the file (used for extension detection)
        data: File bytes
        options: Raw options (merged DSL + explicit kwargs)
        api_key: Optional API key for service mode
        prefer: Processing preference (local/service/local-only/service-only)

    Returns:
        Artifact dict
    """
    options = options or {}
    key = get_api_key(api_key)
    mode = get_prefer(prefer)

    proc, proc_key = _route_processor(filename, data)
    log.debug("routing %s  mode=%s  processor=%s", filename, mode, proc)

    # Resolve raw options against the matched processor's declared schema.
    # Files with no processor get no option warnings.
    resolved: dict[str, Any] = {}
    warnings: list[str] = []
    if proc is not None:
        resolved, warnings = resolve_options(
            get_options(proc_key),
            options,
            context=_option_context(filename, proc_key),
        )

    def _run_local() -> dict:
        result = proc(data, filename=filename, **resolved)
        return _attach_warnings(result, warnings)

    # Determine processing strategy based on mode
    if mode == "service-only":
        # Only use service
        if not key:
            log.warning("service-only mode but no API key for %s", filename)
            return error_artifact(
                filename,
                ERROR_SERVICE,
                "service-only mode but no API key configured",
            )
        return _process_via_service(filename, data, key, options=options)

    elif mode == "local-only":
        # Only use local, fail if no processor or deps missing
        if proc is None:
            log.info("no local processor for %s", filename)
            return _empty_artifact(filename, "no local processor available")
        try:
            return _run_local()
        except Exception as e:
            log.error("local processing failed for %s: %s", filename, e)
            return _artifact_from_exception(filename, e, "local")

    elif mode == "service":
        # Try service first, fall back to local
        if key:
            try:
                result = _process_via_service(filename, data, key, options=options)
                if not result.get("meta", {}).get("error"):
                    return result
            except Exception:
                log.debug("service failed for %s, falling back to local", filename)

        # Fall back to local
        if proc is None:
            return _empty_artifact(filename, "no processor available")
        try:
            return _run_local()
        except Exception as e:
            log.error("processing failed for %s: %s", filename, e)
            return _artifact_from_exception(filename, e, "local")

    else:  # mode == "local" (default)
        # Try local first, fall back to service if deps missing
        if proc is not None:
            try:
                result = _run_local()
                # Typed check: only a missing-dependency result (plus an API
                # key) may trigger service fallback. Other errors are final.
                if not key or not is_missing_dependency(result):
                    return result
                log.info("local dep error for %s, falling back to service", filename)
            except Exception as e:
                if not key:
                    return _artifact_from_exception(filename, e, "local")
                log.info(
                    "local exception for %s, falling back to service: %s",
                    filename,
                    e,
                )

        # No local processor or local failed - try service if key available
        if key:
            try:
                return _process_via_service(filename, data, key, options=options)
            except Exception as e:
                log.error("service processing failed for %s: %s", filename, e)
                return error_artifact(
                    filename, ERROR_SERVICE, f"service processing failed: {e}"
                )

        # No processor and no service
        if proc is None:
            return _empty_artifact(filename, "no processor available")

        # Should not reach here, but just in case
        return error_artifact(filename, ERROR_PROCESSING, "processing failed")


def _process_via_service(
    filename: str,
    data: bytes,
    api_key: str,
    *,
    options: dict[str, Any] | None = None,
) -> dict:
    """Process via the attachments service."""
    from .service import ServiceError, process_via_service

    log.debug("sending %s (%d bytes) to service", filename, len(data))
    try:
        result = process_via_service(
            data, filename=filename, api_key=api_key, options=options
        )
        result.setdefault("meta", {})
        result["meta"]["via"] = "service"
        return result
    except ServiceError as e:
        log.warning("service error for %s: %s", filename, e.message)
        return error_artifact(filename, ERROR_SERVICE, f"service error: {e.message}")


def _source_schema_for(input: str) -> tuple | None:
    """Return the declared source option schema matching *input*, if any.

    GitHub repo-root https URLs share the ``github://`` schema.
    """
    if input.startswith("https://github.com/") and input.count("/") <= 4:
        return source_option_schemas.get("github://")
    for prefix, schema in source_option_schemas.items():
        if input.startswith(prefix):
            return schema
    return None


def _apply_source_options(input: str, options: dict) -> str:
    """Apply source-specific options to the input path.

    Consumes options declared in ``source_option_schemas`` (matching
    canonical names, aliases, and param names) and re-encodes every
    consumed option as a query parameter on the input string, where the
    matching source handler parses it — e.g. ``ref``/``branch``/``tag``
    become ``?ref=...``, which ``_sources.github`` reads. This is the
    generic delivery channel: handler signatures stay
    ``(url) -> [(name, bytes)]``, so a custom source's declared options
    (say ``region`` on ``s3://``) arrive as ``s3://...?region=...``.
    Falsy values are skipped. Unrecognized keys are left untouched WITHOUT
    warnings: they may be processor options resolved later, per file.

    Examples:
        >>> opts = {"ref": "main", "other": "value"}
        >>> _apply_source_options("github://org/repo", opts)
        'github://org/repo?ref=main'
        >>> opts  # ref is consumed
        {'other': 'value'}

        >>> opts = {"branch": "dev"}  # alias for ref
        >>> _apply_source_options("github://org/repo", opts)
        'github://org/repo?ref=dev'

        >>> _apply_source_options("local/file.txt", {"ref": "ignored"})
        'local/file.txt'
    """
    schema = _source_schema_for(input)
    if not schema:
        return input

    consumed: dict[str, Any] = {}
    for option in schema:
        names = {option.name, *option.aliases}
        if option.param:
            names.add(option.param)
        for key in [k for k in options if k in names]:
            consumed[option.param or option.name] = options.pop(key)

    # Generic delivery: append every consumed option as a query parameter
    # on the input string; the matching handler parses it from the URL
    # (github's _clone_github_to_temp reads ?ref=...). Falsy values are
    # skipped — same semantics as the original ``if ref:`` github path.
    for key, value in consumed.items():
        if not value:
            continue
        separator = "&" if "?" in input else "?"
        input = f"{input}{separator}{key}={value}"

    return input


def att(
    input: str,
    *,
    api_key: str | None = None,
    prefer: str | None = None,
    **options: Any,
) -> Artifacts:
    """Turn any input into LLM-ready artifacts.

    This is the main entry point for the attachments library.

    Args:
        input: Source to process. Supports inline options via DSL:
            - Local file: "document.pdf"
            - With options: "document.pdf[pages: 1-4]"
            - Directory: "docs/"
            - URL: "https://example.com/file.pdf[pages: 5-10]"
            - GitHub: "github://owner/repo[ref: main]"
            - Excel: "data.xlsx[sheet: Sales, rows: 100]"
        api_key: Optional API key for service mode. If provided, enables
            fallback to remote processing when local deps are missing.
        prefer: Processing preference:
            - "local" (default): Try local first, fall back to service
            - "service": Try service first, fall back to local
            - "local-only": Only use local processing
            - "service-only": Only use service
        **options: The kwargs twin of the DSL — every DSL option can be
            passed as a keyword argument instead, and explicit kwargs
            override DSL options on collision:
            ``att("d.pdf[pages: 1-1]", pages="2-3")`` processes pages 2-3.

    DSL Syntax:
        path[key: value, key2: value2, ...]

        Values: numbers (300), booleans (true/false), ranges (1-4),
        bare or quoted strings. Keys belong to processors: each processor
        declares its option schema, discoverable at runtime via
        ``att.options(".pdf")`` (or all of them via ``att.options()``).
        Aliases (``page`` -> ``pages``, ``pw`` -> ``password``,
        ``branch`` -> ``ref``, ...) come from those schemas too.

        Options are resolved per file against the matched processor's
        schema. Unknown keys never fail silently: they are dropped with a
        warning in that artifact's ``meta.warnings`` (e.g. "Unknown option
        'sheets' for .xlsx — did you mean 'sheet'?"). When a directory
        unpacks into mixed file types, an option like ``pages`` applies to
        the PDFs and produces per-file unknown-option warnings on the
        others — that is expected. Files with no processor at all get no
        option warnings.

    Returns:
        An :class:`attachments.Artifacts` — a ``list`` subclass whose
        elements remain plain artifact dicts, each with:
            - text: Extracted text content
            - images: List of image dicts
            - audio: List of audio dicts (future)
            - video: List of video dicts (future)
            - meta: Typed metadata (source, kind, error{code,message}, via, ...)

        The container adds interactive sugar around the frozen IR:
        ``repr()`` is a one-line summary, ``str()``/``.text`` is the
        assembled prompt (``render_text``), plus ``.images``, ``.errors``,
        ``.claude()``, ``.openai()``, and ``.chunk()`` shortcuts.

        Errors never raise out of att(); they come back as artifacts with
        ``meta["error"] = {"code": ..., "message": ...}`` (so the return
        value is ALWAYS Artifacts, including every error path).

    Example:
        >>> from attachments import att
        >>> # Simple usage
        >>> artifacts = att("document.pdf")
        >>> # With DSL options
        >>> artifacts = att("document.pdf[pages: 1-4]")
        >>> artifacts = att("report.pdf[pages: 1-10, images: true, dpi: 300]")
        >>> artifacts = att("data.xlsx[sheet: Revenue, rows: 50]")
        >>> # Explicit kwargs override DSL
        >>> artifacts = att("doc.pdf[pages: 1-4]", pages="1-2")  # pages 1-2
        >>> # Discover the options a processor declares
        >>> [o["name"] for o in att.options(".xlsx")]
        ['sheet', 'rows']
    """
    # Parse DSL options from input string
    input, dsl_options = parse_dsl(input)

    # Merge options: explicit kwargs override DSL options
    merged_options = {**dsl_options, **options}

    # Handle source-specific options (e.g., GitHub ref)
    input = _apply_source_options(input, merged_options)

    log.info("att(%r)  prefer=%s  options=%s", input, prefer, merged_options or "{}")

    # Handle unpack with potential service fallback
    try:
        pairs: list[tuple[str, bytes]] = unpack(input)
    except Exception as e:
        # Check if we can use service for unpacking
        key = get_api_key(api_key)
        mode = get_prefer(prefer)

        if key and mode not in ("local-only",):
            try:
                from .service import ServiceError, unpack_via_service

                pairs = unpack_via_service(input, api_key=key)
            except ServiceError as se:
                return Artifacts(
                    [
                        error_artifact(
                            input,
                            ERROR_UNPACK,
                            f"unpack failed: {e}; service: {se.message}",
                        )
                    ]
                )
            except ImportError:
                return Artifacts(
                    [error_artifact(input, ERROR_UNPACK, f"unpack failed: {e}")]
                )
            except Exception as se:
                return Artifacts(
                    [
                        error_artifact(
                            input, ERROR_UNPACK, f"unpack failed: {e}; service: {se}"
                        )
                    ]
                )
        else:
            return Artifacts(
                [error_artifact(input, ERROR_UNPACK, f"unpack failed: {e}")]
            )

    # Process each file
    out = Artifacts()
    for fname, data in pairs:
        artifact = _process_single(
            fname,
            data,
            options=merged_options,
            api_key=api_key,
            prefer=prefer,
        )
        out.append(normalize_artifact(artifact, fname))

    return out
