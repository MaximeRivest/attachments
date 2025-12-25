"""Dependency detection and management for attachments library.

This module provides utilities to check which optional dependencies are
available, enabling graceful degradation and helpful error messages.

Example:
    >>> from attachments import check_deps
    >>> check_deps()
    {'pdf': True, 'xlsx': True, 'docx': False, 'service': True, ...}

    >>> from attachments.deps import require
    >>> require("pdf")  # Raises ImportError with install instructions if missing
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
    "pptx": (("pptx",), "pip install attachments[pptx]"),
    "html": (("bs4", "lxml"), "pip install attachments[html]"),
    "image": (("PIL",), "pip install attachments[image]"),
    "ocr": (("pytesseract", "PIL"), "pip install attachments[ocr]"),
    "audio": (("whisper",), "pip install attachments[audio]"),
    # Sources
    "s3": (("boto3",), "pip install attachments[s3]"),
    "gcs": (("google.cloud.storage",), "pip install attachments[gcs]"),
    "gdrive": (("googleapiclient",), "pip install attachments[gdrive]"),
    # Service
    "service": (("httpx",), "pip install attachments[service]"),
}


@lru_cache(maxsize=128)
def _can_import(module: str) -> bool:
    """Check if a module can be imported without actually importing it.

    Supports alternatives with | syntax: "pypdf|PyPDF2" means either works.
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

    Example:
        >>> check_dep("pdf")
        DepStatus(available=True, modules=('pypdf|PyPDF2', 'pymupdf'), missing=(), ...)
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

    Example:
        >>> check_deps()
        {'pdf': True, 'xlsx': True, 'docx': False, 'service': True, ...}
    """
    return {feature: check_dep(feature).available for feature in DEPENDENCY_MAP}


def require(feature: str) -> None:
    """Require a feature's dependencies, raising helpful error if missing.

    Args:
        feature: Feature name to require

    Raises:
        ImportError: If dependencies are missing, with install instructions

    Example:
        >>> require("pdf")  # Raises if pypdf/pymupdf not installed
    """
    status = check_dep(feature)
    if not status.available:
        raise ImportError(
            f"Missing dependencies for '{feature}': {', '.join(status.missing)}. "
            f"Install with: {status.install_hint}"
        )


def has_service() -> bool:
    """Check if service mode is available (httpx installed)."""
    return check_dep("service").available


def has_local(feature: str) -> bool:
    """Check if local processing is available for a feature."""
    return check_dep(feature).available


def suggest_install(features: list[str]) -> str:
    """Generate install command for multiple features.

    Args:
        features: List of feature names

    Returns:
        Combined pip install command

    Example:
        >>> suggest_install(["pdf", "xlsx", "docx"])
        'pip install attachments[pdf,xlsx,docx]'
    """
    valid = [f for f in features if f in DEPENDENCY_MAP]
    if not valid:
        return ""
    return f"pip install attachments[{','.join(valid)}]"


def clear_cache() -> None:
    """Clear the import check cache. Useful for testing."""
    _can_import.cache_clear()
