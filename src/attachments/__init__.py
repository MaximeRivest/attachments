"""attachments: Turn anything into LLM-ready artifacts.

A universal file and source processing library with zero required dependencies.
Install only what you need, or use the service for zero-dep processing.

Quick Start:
    >>> from attachments import att
    >>> artifacts = att("document.pdf")
    >>> print(artifacts[0]["text"])

With Service Fallback:
    >>> from attachments import att, configure
    >>> configure(api_key="att_...")
    >>> artifacts = att("document.pdf")  # Uses service if local deps missing

Check Available Features:
    >>> from attachments import check_deps
    >>> check_deps()
    {'pdf': True, 'xlsx': False, 'service': True, ...}

Supported Sources (via unpack):
    - Local files and directories
    - ZIP and TAR archives (recursive)
    - GitHub repos: github://owner/repo
    - HTTP/HTTPS URLs
    - Extensible via register_unpack_handler()

Supported Formats (via processors):
    - Text files (20+ extensions)
    - PDF (with pypdf/pymupdf)
    - Excel (with openpyxl/pandas)
    - Extensible via register_processor()

Installation Options:
    pip install attachments              # Core only (text files work)
    pip install attachments[pdf]         # Add PDF support
    pip install attachments[xlsx]        # Add Excel support
    pip install attachments[service]     # Add service mode
    pip install attachments[all-local]   # Everything local
"""

from .config import configure, get_config, reset_config
from .core import att
from .deps import check_dep, check_deps, has_local, has_service
from .dsl import format_dsl, parse_dsl
from .processors import (
    get_processors_copy,
    processor,
    processors,
    register_processor,
    reset_processors,
)
from .unpack import (
    extra_unpack_handlers,
    register_unpack_handler,
    source,
    unpack,
)

__all__ = [
    # Main entry point
    "att",
    # Configuration
    "configure",
    "get_config",
    "reset_config",
    # DSL parsing
    "parse_dsl",
    "format_dsl",
    # Dependency checking
    "check_deps",
    "check_dep",
    "has_local",
    "has_service",
    # Processor registry & decorators
    "processors",
    "register_processor",
    "processor",  # Decorator for multiple extensions
    "reset_processors",
    "get_processors_copy",
    # Unpack registry & decorators
    "unpack",
    "register_unpack_handler",
    "source",  # Decorator for multiple prefixes
    "extra_unpack_handlers",
]

__version__ = "0.1.0"
