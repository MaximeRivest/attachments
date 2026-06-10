"""attachments: Turn anything into LLM-ready artifacts.

A universal file and source processing library with zero required dependencies.
Install only what you need, or use the service for zero-dep processing.

Quick Start::

    from attachments import att

    artifacts = att("document.pdf")
    print(artifacts[0]["text"])

With Service Fallback::

    from attachments import att, configure

    configure(api_key="att_...")
    artifacts = att("document.pdf")  # Uses service if local deps missing

Inline DSL Options::

    att("report.pdf[pages: 1-4, images: true]")
    att("data.xlsx[sheet: Sales, rows: 100]")

Options belong to processors: each processor declares its option schema,
and unknown keys warn ("did you mean ...?") instead of failing silently.
Every DSL option has a keyword-argument twin (kwargs win):

    >>> from attachments import att
    >>> [o["name"] for o in att.options(".pdf")]
    ['pages', 'password', 'images', 'dpi', 'max_pages']

Check Available Features:

    >>> from attachments import check_deps
    >>> deps = check_deps()
    >>> "pdf" in deps and "xlsx" in deps
    True

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
    - PowerPoint (with python-pptx)
    - Images: png/jpg/gif/webp/bmp/tiff (with Pillow)
    - Extensible via register_processor()

Installation Options::

    pip install attachments              # Core only (text files work)
    pip install attachments[pdf]         # Add PDF support
    pip install attachments[xlsx]        # Add Excel support
    pip install attachments[service]     # Add service mode
    pip install attachments[all-local]   # Everything local
"""

from ._options import Option, dsl_schema, options, register_options
from ._processors import (
    get_processors_copy,
    processor,
    processors,
    register_processor,
    reset_processors,
)
from ._unpack import (
    extra_unpack_handlers,
    register_unpack_handler,
    source,
    unpack,
)
from .config import configure, get_config, reset_config
from .core import att
from .deps import check_dep, check_deps, has_local, has_service
from .dsl import format_dsl, parse_dsl
from .render import (
    chunk,
    render_text,
    to_claude_content,
    to_claude_messages,
    to_openai_messages,
)
from .types import (
    ERROR_INVALID_OPTION,
    ERROR_MISSING_DEPENDENCY,
    ERROR_PARSE,
    ERROR_PASSWORD_REQUIRED,
    ERROR_PROCESSING,
    ERROR_SERVICE,
    ERROR_UNPACK,
    Artifact,
    ErrorInfo,
    ImageItem,
    Meta,
    Processor,
    Segment,
    error_artifact,
    is_missing_dependency,
    make_artifact,
    missing_dep_artifact,
    normalize_artifact,
)

__all__ = [
    # Main entry point
    "att",
    # Types & artifact helpers
    "Artifact",
    "ImageItem",
    "Meta",
    "Segment",
    "ErrorInfo",
    "Processor",
    "make_artifact",
    "error_artifact",
    "missing_dep_artifact",
    "is_missing_dependency",
    "normalize_artifact",
    # Error codes
    "ERROR_MISSING_DEPENDENCY",
    "ERROR_PASSWORD_REQUIRED",
    "ERROR_PARSE",
    "ERROR_UNPACK",
    "ERROR_SERVICE",
    "ERROR_INVALID_OPTION",
    "ERROR_PROCESSING",
    # Configuration
    "configure",
    "get_config",
    "reset_config",
    # DSL parsing
    "parse_dsl",
    "format_dsl",
    # Option schemas (per-processor DSL options)
    "Option",
    "options",
    "register_options",
    "dsl_schema",
    # Dependency checking
    "check_deps",
    "check_dep",
    "has_local",
    "has_service",
    # Last-mile rendering & adapters (attachments.render)
    "render_text",
    "to_claude_content",
    "to_claude_messages",
    "to_openai_messages",
    "chunk",
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

# Runtime discoverability: att.options(".pdf") -> declared option dicts.
att.options = options  # type: ignore[attr-defined]

__version__ = "1.0.0"  # see VISION.md
