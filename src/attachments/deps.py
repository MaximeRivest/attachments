"""Dependency detection and management for attachments library.

This module provides utilities to check which optional dependencies are
available, enabling graceful degradation and helpful error messages.

Example:

    >>> from attachments import check_deps
    >>> deps = check_deps()
    >>> isinstance(deps, dict) and "pdf" in deps
    True

    >>> from attachments.deps import require
    >>> # require("pdf")  # Raises ImportError with install instructions if missing
"""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from typing import NamedTuple


class DepStatus(NamedTuple):
    """Status of a dependency group."""

    available: bool
    modules: tuple[str, ...]
    missing: tuple[str, ...]
    install_hint: str


# Mapping of feature -> (required_modules, install_command)
# For modules with alternatives, we check if ANY is available
DEPENDENCY_MAP: dict[str, tuple[tuple[str, ...], str]] = {
    # Processors
    "pdf": (("pypdf|PyPDF2", "pymupdf"), "pip install attachments[pdf]"),
    "pdf-text": (("pypdf|PyPDF2",), "pip install pypdf"),
    "pdf-images": (("pymupdf",), "pip install pymupdf"),
    "pdf-fallback": (("pdfminer",), "pip install attachments[pdf-fallback]"),
    "xlsx": (("openpyxl",), "pip install attachments[xlsx]"),
    "xlsx-pandas": (("pandas", "openpyxl"), "pip install attachments[xlsx-pandas]"),
    "docx": (("docx",), "pip install attachments[docx]"),
    "html": (("bs4", "lxml"), "pip install attachments[html]"),
    # Future processors/sources (pptx, image, ocr, audio, s3, gcs, gdrive, ...)
    # are added here together with their processor module and pyproject extra.
    # Service
    "service": (("httpx",), "pip install attachments[service]"),
}


@lru_cache(maxsize=128)
def _can_import(module: str) -> bool:
    """Check if a module can be imported without actually importing it.

    Supports alternatives with | syntax: "pypdf|PyPDF2" means either works.

    Examples:
        >>> _can_import("os")  # stdlib always available
        True
        >>> _can_import("nonexistent_module_xyz")
        False
        >>> _can_import("os|sys")  # Either works
        True
    """
    # Handle alternatives (e.g., "pypdf|PyPDF2")
    if "|" in module:
        alternatives = module.split("|")
        return any(_can_import(alt) for alt in alternatives)

    # Handle nested modules like "google.cloud.storage"
    top_level = module.split(".")[0]
    return importlib.util.find_spec(top_level) is not None


def check_dep(feature: str) -> DepStatus:
    """Check if a specific feature's dependencies are available.

    Args:
        feature: Feature name (e.g., "pdf", "xlsx", "service")

    Returns:
        DepStatus with availability info and install hints

    Examples:
        >>> status = check_dep("pdf")
        >>> status.modules
        ('pypdf|PyPDF2', 'pymupdf')
        >>> status.install_hint
        'pip install attachments[pdf]'
        >>> isinstance(status.available, bool)
        True

        >>> check_dep("invalid_feature")  # doctest: +IGNORE_EXCEPTION_DETAIL
        Traceback (most recent call last):
        ValueError: Unknown feature: invalid_feature. Valid: ...
    """
    if feature not in DEPENDENCY_MAP:
        valid = list(DEPENDENCY_MAP.keys())
        raise ValueError(f"Unknown feature: {feature}. Valid: {valid}")

    modules, install_hint = DEPENDENCY_MAP[feature]
    missing = tuple(m for m in modules if not _can_import(m))

    return DepStatus(
        available=len(missing) == 0,
        modules=modules,
        missing=missing,
        install_hint=install_hint,
    )


def check_deps() -> dict[str, bool]:
    """Check which optional features are available.

    Returns:
        Dict mapping feature names to availability boolean

    Examples:
        >>> deps = check_deps()
        >>> isinstance(deps, dict)
        True
        >>> "pdf" in deps and "xlsx" in deps and "service" in deps
        True
        >>> all(isinstance(v, bool) for v in deps.values())
        True
    """
    return {feature: check_dep(feature).available for feature in DEPENDENCY_MAP}


def require(feature: str) -> None:
    """Require a feature's dependencies, raising helpful error if missing.

    Args:
        feature: Feature name to require

    Raises:
        ImportError: If dependencies are missing, with install instructions

    Examples:
        >>> # This would raise ImportError if pdf deps not installed:
        >>> # require("pdf")

        >>> require("nonexistent")  # doctest: +IGNORE_EXCEPTION_DETAIL
        Traceback (most recent call last):
        ValueError: Unknown feature: nonexistent. Valid: ...
    """
    status = check_dep(feature)
    if not status.available:
        raise ImportError(
            f"Missing dependencies for '{feature}': {', '.join(status.missing)}. "
            f"Install with: {status.install_hint}"
        )


def has_service() -> bool:
    """Check if service mode is available (httpx installed).

    Examples:
        >>> isinstance(has_service(), bool)
        True
    """
    return check_dep("service").available


def has_local(feature: str) -> bool:
    """Check if local processing is available for a feature.

    Examples:
        >>> isinstance(has_local("pdf"), bool)
        True
        >>> isinstance(has_local("xlsx"), bool)
        True
    """
    return check_dep(feature).available


def suggest_install(features: list[str]) -> str:
    """Generate install command for multiple features.

    Args:
        features: List of feature names

    Returns:
        Combined pip install command

    Examples:
        >>> suggest_install(["pdf", "xlsx", "docx"])
        'pip install attachments[pdf,xlsx,docx]'
        >>> suggest_install(["pdf"])
        'pip install attachments[pdf]'
        >>> suggest_install(["invalid_only"])
        ''
        >>> suggest_install([])
        ''
    """
    valid = [f for f in features if f in DEPENDENCY_MAP]
    if not valid:
        return ""
    return f"pip install attachments[{','.join(valid)}]"


def clear_cache() -> None:
    """Clear the import check cache. Useful for testing.

    Examples:
        >>> clear_cache()  # No error, clears LRU cache
    """
    _can_import.cache_clear()
