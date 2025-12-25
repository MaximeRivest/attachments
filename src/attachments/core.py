"""Core processing pipeline for attachments.

This module provides the main `att()` function that orchestrates:
1. Unpacking input sources into (filename, bytes) pairs
2. Routing each file to the appropriate processor
3. Processing with local deps or service fallback
4. Normalizing output to consistent artifact format
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from .config import get_api_key, get_prefer
from .dsl import parse_dsl
from .processors import processors
from .unpack import unpack
from .utils import is_text_bytes


def _route_processor(filename: str, data: bytes) -> Callable[..., dict] | None:
    """Find the appropriate processor for a file.

    Returns None if no processor found (will trigger service fallback).
    """
    ext = os.path.splitext(filename)[1].lower()
    proc = processors.get(ext)
    if proc is None and is_text_bytes(data):
        proc = processors.get("__text__")
    return proc


def _error_artifact(source: str, error: str) -> dict:
    """Create a standardized error artifact."""
    return {
        "text": "",
        "images": [],
        "audio": [],
        "video": [],
        "flags": {"source": source, "error": error},
    }


def _empty_artifact(source: str, note: str) -> dict:
    """Create an empty artifact with a note."""
    return {
        "text": "",
        "images": [],
        "audio": [],
        "video": [],
        "flags": {"source": source, "note": note},
    }


def _has_meaningful_error(artifact: dict) -> bool:
    """Check if artifact has an error indicating missing deps."""
    flags = artifact.get("flags", {})
    error = flags.get("error", "")
    # Common patterns indicating missing dependencies
    dep_indicators = [
        "requires",
        "not installed",
        "unavailable",
        "ImportError",
        "ModuleNotFoundError",
        "no module",
    ]
    return any(ind.lower() in error.lower() for ind in dep_indicators)


def _is_empty_result(artifact: dict) -> bool:
    """Check if artifact has no meaningful content."""
    return (
        not artifact.get("text", "").strip()
        and not artifact.get("images", [])
        and not artifact.get("audio", [])
        and not artifact.get("video", [])
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

    # Determine processing strategy based on mode
    if mode == "service-only":
        # Only use service
        if not key:
            return _error_artifact(
                filename, "service-only mode but no API key configured"
            )
        return _process_via_service(filename, data, key, **options)

    elif mode == "local-only":
        # Only use local, fail if no processor or deps missing
        if proc is None:
            return _empty_artifact(filename, "no local processor available")
        try:
            return proc(data, filename=filename, **options)
        except Exception as e:
            return _error_artifact(filename, f"local processing failed: {e}")

    elif mode == "service":
        # Try service first, fall back to local
        if key:
            try:
                result = _process_via_service(filename, data, key, **options)
                if not result.get("flags", {}).get("error"):
                    return result
            except Exception:
                pass  # Fall through to local

        # Fall back to local
        if proc is None:
            return _empty_artifact(filename, "no processor available")
        try:
            return proc(data, filename=filename, **options)
        except Exception as e:
            return _error_artifact(filename, f"processing failed: {e}")

    else:  # mode == "local" (default)
        # Try local first, fall back to service if deps missing
        if proc is not None:
            try:
                result = proc(data, filename=filename, **options)
                # Check if local succeeded or failed due to missing deps
                if not _has_meaningful_error(result) or not key:
                    return result
                # Has dep error and we have API key - try service
            except Exception as e:
                if not key:
                    return _error_artifact(filename, f"local processing failed: {e}")
                # Fall through to service

        # No local processor or local failed - try service if key available
        if key:
            try:
                return _process_via_service(filename, data, key, **options)
            except Exception as e:
                return _error_artifact(filename, f"service processing failed: {e}")

        # No processor and no service
        if proc is None:
            return _empty_artifact(filename, "no processor available")

        # Should not reach here, but just in case
        return _error_artifact(filename, "processing failed")


def _process_via_service(
    filename: str,
    data: bytes,
    api_key: str,
    **options: Any,
) -> dict:
    """Process via the attachments service."""
    from .service import ServiceError, process_via_service

    try:
        result = process_via_service(
            data, filename=filename, api_key=api_key, **options
        )
        result.setdefault("flags", {})
        result["flags"]["via"] = "service"
        return result
    except ServiceError as e:
        return _error_artifact(filename, f"service error: {e.message}")


def _normalize_artifact(artifact: dict, source: str) -> dict:
    """Ensure artifact has all required keys with correct types."""
    artifact.setdefault("text", "")
    artifact.setdefault("images", [])
    artifact.setdefault("audio", [])
    artifact.setdefault("video", [])
    artifact.setdefault("flags", {})
    artifact["flags"].setdefault("source", source)
    return artifact


def _apply_source_options(input: str, options: dict) -> str:
    """Apply source-specific options to the input path.

    Transforms DSL options into URL parameters for sources that support them.
    For example, adds ?ref=main to GitHub URLs.
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
            - flags: Metadata including source, errors, processing info

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
                    _error_artifact(input, f"unpack failed: {e}; service: {se.message}")
                ]
            except ImportError:
                return [_error_artifact(input, f"unpack failed: {e}")]
            except Exception as se:
                return [_error_artifact(input, f"unpack failed: {e}; service: {se}")]
        else:
            return [_error_artifact(input, f"unpack failed: {e}")]

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
        out.append(_normalize_artifact(artifact, fname))

    return out
