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
from collections.abc import Callable
from typing import Any

from .config import get_api_key, get_prefer
from .dsl import parse_dsl
from .processors import processors
from .types import (
    ERROR_MISSING_DEPENDENCY,
    ERROR_PROCESSING,
    ERROR_SERVICE,
    ERROR_UNPACK,
    error_artifact,
    is_missing_dependency,
    make_artifact,
    normalize_artifact,
)
from .unpack import unpack
from .utils import is_text_bytes

log = logging.getLogger("attachments.core")


def _route_processor(filename: str, data: bytes) -> Callable[..., dict] | None:
    """Find the appropriate processor for a file.

    Returns None if no processor found (will trigger service fallback).
    """
    ext = os.path.splitext(filename)[1].lower()
    proc = processors.get(ext)
    if proc is None and is_text_bytes(data):
        proc = processors.get("__text__")
    return proc


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


def _process_single(
    filename: str,
    data: bytes,
    *,
    api_key: str | None = None,
    prefer: str | None = None,
    **options: Any,
) -> dict:
    """Process a single file with local/service fallback logic.

    Args:
        filename: Name of the file (used for extension detection)
        data: File bytes
        api_key: Optional API key for service mode
        prefer: Processing preference (local/service/local-only/service-only)
        **options: Passed to processor

    Returns:
        Artifact dict
    """
    key = get_api_key(api_key)
    mode = get_prefer(prefer)

    proc = _route_processor(filename, data)
    log.debug("routing %s  mode=%s  processor=%s", filename, mode, proc)

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
        return _process_via_service(filename, data, key, **options)

    elif mode == "local-only":
        # Only use local, fail if no processor or deps missing
        if proc is None:
            log.info("no local processor for %s", filename)
            return _empty_artifact(filename, "no local processor available")
        try:
            return proc(data, filename=filename, **options)
        except Exception as e:
            log.error("local processing failed for %s: %s", filename, e)
            return _artifact_from_exception(filename, e, "local")

    elif mode == "service":
        # Try service first, fall back to local
        if key:
            try:
                result = _process_via_service(filename, data, key, **options)
                if not result.get("meta", {}).get("error"):
                    return result
            except Exception:
                log.debug("service failed for %s, falling back to local", filename)

        # Fall back to local
        if proc is None:
            return _empty_artifact(filename, "no processor available")
        try:
            return proc(data, filename=filename, **options)
        except Exception as e:
            log.error("processing failed for %s: %s", filename, e)
            return _artifact_from_exception(filename, e, "local")

    else:  # mode == "local" (default)
        # Try local first, fall back to service if deps missing
        if proc is not None:
            try:
                result = proc(data, filename=filename, **options)
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
                return _process_via_service(filename, data, key, **options)
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
    **options: Any,
) -> dict:
    """Process via the attachments service."""
    from .service import ServiceError, process_via_service

    log.debug("sending %s (%d bytes) to service", filename, len(data))
    try:
        result = process_via_service(
            data, filename=filename, api_key=api_key, **options
        )
        result.setdefault("meta", {})
        result["meta"]["via"] = "service"
        return result
    except ServiceError as e:
        log.warning("service error for %s: %s", filename, e.message)
        return error_artifact(filename, ERROR_SERVICE, f"service error: {e.message}")


def _apply_source_options(input: str, options: dict) -> str:
    """Apply source-specific options to the input path.

    Transforms DSL options into URL parameters for sources that support them.
    For example, adds ?ref=main to GitHub URLs.

    Examples:
        >>> opts = {"ref": "main", "other": "value"}
        >>> _apply_source_options("github://org/repo", opts)
        'github://org/repo?ref=main'
        >>> opts  # ref is consumed
        {'other': 'value'}

        >>> _apply_source_options("local/file.txt", {"ref": "ignored"})
        'local/file.txt'
    """
    # GitHub: add ref as query parameter
    if input.startswith("github://") or (
        input.startswith("https://github.com/") and input.count("/") <= 4
    ):
        ref = options.pop("ref", None)
        if ref:
            separator = "&" if "?" in input else "?"
            input = f"{input}{separator}ref={ref}"

    return input


def att(
    input: str,
    *,
    api_key: str | None = None,
    prefer: str | None = None,
    **options: Any,
) -> list[dict]:
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
        **options: Passed to processors (override DSL options). Common:
            - password: PDF password
            - page_start/page_end: PDF page range (0-based)
            - render_images: PDF image rendering
            - sheet: Excel sheet selection
            - max_rows: Excel row limit

    DSL Syntax:
        path[key: value, key2: value2, ...]

        Keys (with aliases):
            pages, page     -> page_start, page_end (1-based in DSL)
            sheet           -> sheet
            rows            -> max_rows
            images, render  -> render_images
            dpi             -> images_dpi
            password, pw    -> password
            branch, ref     -> ref (for GitHub)

        Values:
            - Numbers: 100, 42
            - Booleans: true, false, yes, no
            - Ranges: 1-4 (for pages)
            - Strings: anything else

    Returns:
        List of artifact dicts, each with:
            - text: Extracted text content
            - images: List of image dicts
            - audio: List of audio dicts (future)
            - video: List of video dicts (future)
            - meta: Typed metadata (source, kind, error{code,message}, via, ...)

        Errors never raise out of att(); they come back as artifacts with
        ``meta["error"] = {"code": ..., "message": ...}``.

    Example:
        >>> from attachments import att
        >>> # Simple usage
        >>> artifacts = att("document.pdf")
        >>> # With DSL options
        >>> artifacts = att("document.pdf[pages: 1-4]")
        >>> artifacts = att("report.pdf[pages: 1-10, images: true, dpi: 300]")
        >>> artifacts = att("data.xlsx[sheet: Revenue, rows: 50]")
        >>> # Explicit options override DSL
        >>> artifacts = att("doc.pdf[pages: 1-4]", page_end=2)  # pages 1-2
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
                return [
                    error_artifact(
                        input,
                        ERROR_UNPACK,
                        f"unpack failed: {e}; service: {se.message}",
                    )
                ]
            except ImportError:
                return [error_artifact(input, ERROR_UNPACK, f"unpack failed: {e}")]
            except Exception as se:
                return [
                    error_artifact(
                        input, ERROR_UNPACK, f"unpack failed: {e}; service: {se}"
                    )
                ]
        else:
            return [error_artifact(input, ERROR_UNPACK, f"unpack failed: {e}")]

    # Process each file
    out: list[dict] = []
    for fname, data in pairs:
        artifact = _process_single(
            fname,
            data,
            api_key=api_key,
            prefer=prefer,
            **merged_options,
        )
        out.append(normalize_artifact(artifact, fname))

    return out
