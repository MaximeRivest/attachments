# Attachments Development Guide

## Architecture Overview

Attachments uses a **zero required dependencies** architecture with smart fallback to a remote service. This enables:

1. **Minimal installs** - Users install only what they need
2. **Service fallback** - When local deps are missing, use the API
3. **Graceful degradation** - Never crash, always return useful artifacts

```
┌─────────────────────────────────────────────────────┐
│  att("file.pdf", prefer="local")                    │
└─────────────────────┬───────────────────────────────┘
                      │
         ┌────────────▼────────────┐
         │ Has local processor?    │
         │ (pypdf installed?)      │
         └────────────┬────────────┘
                ┌─────┴─────┐
              Yes          No
                │            │
         ┌──────▼──────┐    │
         │ Try local   │    │
         └──────┬──────┘    │
                │           │
         ┌──────▼──────┐    │
         │ Succeeded?  ├────┤
         └──────┬──────┘    │
              Yes          No + has API key
                │            │
                │     ┌──────▼──────┐
                │     │ Try service │
                │     └──────┬──────┘
                │            │
         ┌──────▼────────────▼──────┐
         │     Return artifact      │
         └──────────────────────────┘
```

## Public API

```python
from attachments import att, configure, check_deps

# Check what's available locally
check_deps()
# {'pdf': True, 'xlsx': True, 'service': False, ...}

# Configure service fallback
configure(api_key="att_...", prefer="local")

# Process - uses local if available, service as fallback
artifacts = att("document.pdf")

# Force modes
att("doc.pdf", prefer="local-only")    # Never use service
att("doc.pdf", prefer="service-only")  # Always use service
att("doc.pdf", prefer="service")       # Try service first
```

## Installation Options

```bash
pip install attachments              # Core only (text files work)
pip install attachments[pdf]         # Add PDF support
pip install attachments[xlsx]        # Add Excel support
pip install attachments[docx]        # Add Word support
pip install attachments[pptx]        # Add PowerPoint support
pip install attachments[html]        # Add HTML support
pip install attachments[image]       # Add image support (Pillow)
pip install attachments[service]     # Add service mode (httpx)
pip install attachments[clipboard]   # CLI clipboard support (`att --copy`)
pip install attachments[office]      # xlsx + docx + pptx
pip install attachments[ocr]         # OCR for scanned PDFs/images (large: pulls onnxruntime)
pip install attachments[audio]       # Audio transcription (large: pulls faster-whisper/ctranslate2)
pip install attachments[all-local]   # Everything currently shipped (except ocr/audio — too big)
pip install attachments[server]      # Self-hosted server (= all-local + ocr + audio)
```

---

## Building New Processors

Processors convert file bytes into artifacts. Each processor handles one or more file extensions.

### Quick Start (Decorator Pattern)

```python
# my_processors.py
from attachments import Option, make_artifact, missing_dep_artifact, processor

@processor(
    ".docx", ".doc",
    options=(
        Option(
            "images", "bool",
            help="Extract embedded images.",
            example="images: true",
        ),
    ),
)
def word_processor(data: bytes, **options) -> dict:
    """Process Word documents."""
    filename = options.get("filename", "document.docx")
    try:
        from docx import Document
    except ImportError:
        # Typed missing-dependency signal (drives service fallback)
        return missing_dep_artifact(filename, "docx")

    # ... process document ...
    return make_artifact(text=extracted_text, meta={"kind": "document"})
```

That's it! The decorator registers the processor AND its declared option
schema. The schema powers everything for free: DSL/kwarg resolution with
"did you mean" warnings for unknown keys, `att.options(".docx")` runtime
discovery, `att --options`, and the server's `GET /options` export. An
`Option` declares `name`, `type` (`str`, `int`, `float`, `bool`, `pages`,
`bool_or_auto`, `str_or_int`), plus optional `aliases`, `param` (the kwarg
name your function receives, when it differs from the DSL key), `default`,
`help`, and `example`. Options only reach your processor if they are
declared in its schema; an empty tuple (`options=()`) documents that your
format takes none. Either way — undeclared schema or declared-empty — any
DSL/kwarg option on your format is dropped with an "Unknown option"
warning in that artifact's `meta.warnings`; it is never passed through.

> **Migration note (pre-schema processors):** processors used to receive
> ALL raw DSL/kwarg options as `**options`. Since option schemas were
> introduced, a processor receives ONLY the options declared in its
> schema (plus `filename`). A third-party processor written against the
> old pass-through behavior silently stops receiving its options until it
> declares them via `options=(...)` on `@processor` (or
> `register_options`).

### Alternative: Function Calls

```python
from attachments import Option, register_options, register_processor

def my_processor(data: bytes, **options) -> dict:
    ...

register_processor(".myf", my_processor)
register_options(".myf", (Option("depth", "int", help="Parse depth."),))
```

### Full Example

Create `src/attachments/_processors/myformat.py`:

```python
"""Processor for MyFormat files (.myf)."""

from __future__ import annotations

from typing import Any

from .._options import Option
from ..types import (
    ERROR_PARSE,
    error_artifact,
    make_artifact,
    missing_dep_artifact,
)
from . import processor  # Use the decorator


@processor(
    ".myf",
    ".myformat",
    options=(
        Option(
            "depth", "int", default=1,
            help="How many levels to parse.",
            example="depth: 3",
        ),
    ),
)
def myformat_processor(data: bytes, **options: Any) -> dict[str, Any]:
    """Convert MyFormat bytes to an artifact.

    Args:
        data: Raw file bytes
        **options: Processing options (filename, custom options, etc.)

    Returns:
        Artifact dict with text, images, audio, video, meta
    """
    filename = options.get("filename", "unknown")

    # Try to import the optional dependency
    try:
        import myformat_lib
    except ImportError:
        # Typed missing-dependency artifact: core routing falls back to
        # the service when an API key is configured. The install hint is
        # looked up from deps.DEPENDENCY_MAP automatically.
        return missing_dep_artifact(filename, "myformat")

    # Process the file
    try:
        parsed = myformat_lib.parse(data)
        text = parsed.get_text()
        images = [
            {
                "name": f"{filename}-{i}.png",
                "mimetype": "image/png",
                "bytes": img.to_png(),
                "page": i + 1,
            }
            for i, img in enumerate(parsed.images)
        ]

        return make_artifact(
            text=text,
            images=images,
            meta={
                "kind": "myformat",
                # Backend/diagnostic details always go under meta.extra
                "extra": {"filename": filename, "version": parsed.version},
            },
        )
    except Exception as e:
        return error_artifact(filename, ERROR_PARSE, f"Failed to parse MyFormat: {e}")
```

### Step 2: Import in `_processors/__init__.py`

Add the import to trigger self-registration:

```python
# Import modules to trigger self-registration
from . import text as _text
from . import xlsx as _xlsx
from . import pdf as _pdf
from . import myformat as _myformat  # ADD THIS
```

### Step 3: Add Dependencies to `pyproject.toml`

```toml
[project.optional-dependencies]
# ... existing ...

# Add your new processor
myformat = [
    "myformat-lib>=1.0",
]

# Update bundles if appropriate
all-local = [
    "attachments[pdf,pdf-fallback,xlsx-pandas,docx,html,myformat]",
]
```

### Step 4: Register in `deps.py`

Add to `DEPENDENCY_MAP`:

```python
DEPENDENCY_MAP: dict[str, tuple[tuple[str, ...], str]] = {
    # ... existing ...

    # Add your processor
    "myformat": (("myformat_lib",), "pip install attachments[myformat]"),
}
```

### Step 5: Add Tests

Create `tests/test_myformat.py`:

```python
import pytest
from attachments import ERROR_MISSING_DEPENDENCY, att, check_dep


def test_myformat_missing_dep():
    """Test graceful handling when myformat-lib not installed."""
    if check_dep("myformat").available:
        pytest.skip("myformat-lib is installed")

    # Should return a typed error artifact, not raise
    result = att("test.myf")
    error = result[0]["meta"]["error"]
    assert error["code"] == ERROR_MISSING_DEPENDENCY
    assert "pip install" in error["message"]


@pytest.mark.skipif(
    not check_dep("myformat").available,
    reason="myformat-lib not installed"
)
def test_myformat_processing():
    """Test actual processing when dep is available."""
    # Create test file or use fixture
    result = att("tests/fixtures/sample.myf")
    assert result[0]["text"]
    assert result[0]["meta"]["kind"] == "myformat"
```

---

## Building New Sources

Source handlers resolve input strings (URLs, paths, schemes) into `(filename, bytes)` pairs.
Built-in sources live in the `src/attachments/_sources/` package — one module
per source, mirroring `_processors/` (see the
[Module Structure](#module-structure) map).

Checklist (symmetric to [Building New Processors](#building-new-processors)):

- [ ] **One module** in `src/attachments/_sources/` (e.g. `_sources/s3.py`)
      — or your own package for third-party handlers
- [ ] **Register at import time** (`@source(...)` / `register_unpack_handler`)
      + an import line in `_sources/__init__.py` for built-ins.
      **Placement matters**: built-in modules must use the relative import
      `from . import source`, and their import line goes in the block at the
      **bottom** of `_sources/__init__.py` — after the registry is defined.
      A top-of-file import (or `from attachments import source` inside
      `_sources/`) is circular and breaks all of `import attachments`
      (see [Step 2](#step-2-register-the-handler))
- [ ] **Optional source option schema** via `register_options("s3://", ...)`
      immediately followed by `snapshot_option_defaults()` — see how
      `_sources/github.py` declares `ref`. Without the snapshot call,
      `reset_options()` / `reset_processors()` (which the autouse fixture in
      `tests/conftest.py` runs after every test) silently wipes the schema.
      Declared options are consumed from the DSL and delivered to your
      handler as query parameters on the input:
      `s3://bucket/key[region: us-east-1]` reaches the handler as
      `s3://bucket/key?region=us-east-1` — parse them the way
      `_sources/github.py` parses `?ref=`
- [ ] **`deps.py` entry + `pyproject.toml` extra** if it needs dependencies
- [ ] **Tests** in `tests/test_sources/`, including a download path that
      respects the guards in `_sources/_guards.py` (size caps, SSRF guard
      for anything fetched over HTTP)
- [ ] **Run `uv run python scripts/gen_dsl_assets.py`** if you added an
      option schema (regenerates `__init__.pyi`, `spec/dsl-schema.json`,
      `docs/dsl-options.md`)

### Quick Start (Decorator Pattern)

For third-party handlers in your own package:

```python
# my_sources.py — your own package, NOT inside attachments/_sources/
from attachments import source

@source("s3://", "s3a://")
def s3_handler(url: str) -> list[tuple[str, bytes]]:
    """Fetch files from S3."""
    try:
        import boto3
    except ImportError:
        raise ImportError("pip install attachments[s3]")

    # Parse URL, fetch files...
    return [("file.txt", file_bytes)]
```

Inside `attachments/_sources/`, this top-level import is circular (the
`attachments` package is still initializing when `_sources/` modules are
imported) — built-in modules must use the relative form
`from . import source` instead. See the Full Example below.

### Alternative: Function Call

```python
from attachments import register_unpack_handler

def my_handler(url: str) -> list[tuple[str, bytes]]:
    ...

register_unpack_handler("myproto://", my_handler)
```

### Full Example

Create `src/attachments/_sources/s3.py` (or your own package's module):

```python
"""S3 source handler for attachments."""

from __future__ import annotations

# Built-in modules MUST use this relative import — `from attachments
# import source` is circular inside `_sources/`. In your own package,
# use `from attachments import source` instead.
from . import source


@source("s3://")
def s3_handler(url: str) -> list[tuple[str, bytes]]:
    """Fetch files from S3.

    Args:
        url: S3 URL like "s3://bucket/key" or "s3://bucket/prefix/"

    Returns:
        List of (filename, bytes) tuples
    """
    try:
        import boto3
    except ImportError:
        raise ImportError(
            "S3 support requires boto3. "
            "Install with: pip install attachments[s3]"
        )

    # Parse the URL
    # s3://bucket/key or s3://bucket/prefix/
    if not url.startswith("s3://"):
        raise ValueError(f"Not an S3 URL: {url}")

    path = url[5:]  # Remove "s3://"
    parts = path.split("/", 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ""

    s3 = boto3.client("s3")

    # Check if it's a prefix (directory-like) or single object
    if key.endswith("/") or not key:
        # List objects with prefix
        result = s3.list_objects_v2(Bucket=bucket, Prefix=key)
        files = []
        for obj in result.get("Contents", []):
            obj_key = obj["Key"]
            if obj_key.endswith("/"):
                continue  # Skip "directories"
            response = s3.get_object(Bucket=bucket, Key=obj_key)
            data = response["Body"].read()
            # Use relative path from prefix as filename
            filename = obj_key[len(key):] if key else obj_key
            files.append((filename, data))
        return files
    else:
        # Single object
        response = s3.get_object(Bucket=bucket, Key=key)
        data = response["Body"].read()
        filename = key.split("/")[-1]
        return [(filename, data)]
```

### Step 2: Register the Handler

For third-party handlers (the common case), registration is the decorator or
function call shown above — `@source("s3://")` /
`register_unpack_handler("s3://", s3_handler)` adds the prefix to the public
`extra_unpack_handlers` registry, which `unpack()` consults before its
built-in resolution.

For handlers contributed to the library itself, the module lives in the
`_sources/` package (e.g. `src/attachments/_sources/s3.py`), uses the
relative import `from . import source` (see the Full Example above), and
gets an import line in the block at the **bottom** of
`_sources/__init__.py` — after `register_unpack_handler` / `source` are
defined, mirroring `_processors/__init__.py`:

```python
# Import built-in source modules LAST so they can use the registry defined
# above (...) — same layout as _processors/__init__.py.
from .archives import _explode_archive_bytes, _is_raw_archive_name  # noqa: E402
from .github import _clone_github_to_temp, _is_github_repo_root_url  # noqa: E402
from .http import _download_http_or_https  # noqa: E402
from .local import _walk_directory  # noqa: E402
from . import s3 as _s3  # noqa: E402,F401  # ADD THIS
```

Do **not** put the import at the top of `_sources/__init__.py`: it would run
before the registry exists and break all of `import attachments` with
`ImportError: cannot import name 'source' from partially initialized module`.

Note that the historical built-ins predate the registry and don't use
`@source`: `github://` dispatch is hardwired inside `unpack()` itself, and
`_sources/github.py` registers only its *option schema* (`ref`) via
`register_options` + `snapshot_option_defaults`. Copy `github.py` for the
schema pattern and the Full Example above for handler registration.

### Step 3: Add Dependencies to `pyproject.toml`

```toml
[project.optional-dependencies]
# ... existing ...

s3 = [
    "boto3>=1.34",
]

# Update cloud bundle
cloud = [
    "attachments[s3,gcs,gdrive]",
]
```

### Step 4: Register in `deps.py`

```python
DEPENDENCY_MAP = {
    # ... existing ...
    "s3": (("boto3",), "pip install attachments[s3]"),
}
```

### Step 5: Add Tests

```python
import pytest
from attachments import att, check_dep
from unittest.mock import patch, MagicMock


def test_s3_missing_dep():
    """Test error when boto3 not installed."""
    if check_dep("s3").available:
        pytest.skip("boto3 is installed")

    result = att("s3://bucket/key.pdf")
    assert "error" in result[0]["meta"]


@pytest.mark.skipif(
    not check_dep("s3").available,
    reason="boto3 not installed"
)
def test_s3_with_mock():
    """Test S3 handling with mocked boto3."""
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {
        "Body": MagicMock(read=lambda: b"PDF content here")
    }

    with patch("boto3.client", return_value=mock_s3):
        result = att("s3://mybucket/document.pdf")

    assert len(result) == 1
    mock_s3.get_object.assert_called_once()
```

---

## Dependency Management Checklist

When adding a new processor or source:

- [ ] **1. Create the module** with try/except imports
- [ ] **2. Add to `pyproject.toml`** optional dependencies
- [ ] **3. Add to `deps.py`** DEPENDENCY_MAP
- [ ] **4. Add import** to `_processors/__init__.py` (for built-in processors)
- [ ] **5. Update bundles** in pyproject.toml (`office`, `all-local`)
- [ ] **6. Add tests** for both missing-dep and installed cases
- [ ] **7. Update dev dependencies** if needed for testing

### Dependency Naming Conventions

The extras that exist today: `pdf`, `pdf-fallback`, `xlsx`, `xlsx-pandas`,
`docx`, `pptx`, `html`, `image`, `service`, `clipboard`, `office`,
`all-local`, `server`.
New extras follow these conventions:

```toml
[project.optional-dependencies]
# Processors: named after format
pdf = [...]
xlsx = [...]
docx = [...]

# Processors with alternatives: use descriptive suffix
pdf-fallback = ["pdfminer.six"]       # Alternative backend
xlsx-pandas = ["pandas", "openpyxl"]  # Enhanced version

# Future sources: named after service/protocol (s3, gcs, gdrive, ...)

# Bundles: descriptive groupings
office = ["attachments[xlsx,docx,pptx]"]
all-local = ["attachments[pdf,pdf-fallback,xlsx-pandas,docx,pptx,html,image]"]
server = ["attachments[all-local]"]

# Service mode
service = ["httpx>=0.27"]
```

### Error Message Convention

Always include install instructions in error messages:

```python
# Good
"PDF processing requires pypdf. Install with: pip install attachments[pdf]"

# Bad
"pypdf not found"
"ImportError: No module named 'pypdf'"
```

---

## Module Structure

```
src/attachments/
├── __init__.py              # Public API exports
├── __init__.pyi             # GENERATED typing stub (scripts/gen_dsl_assets.py):
│                            #   kwargs autocomplete for att() — do not edit
├── core.py                  # Main att() function, routing logic
├── _artifacts.py            # Artifacts container att() returns (list subclass;
│                            #   repr/str/.claude()/.openai()/.chunk() sugar)
├── config.py                # Global configuration
├── deps.py                  # Dependency detection
├── service.py               # Remote API client
├── server.py                # Self-hosted server (stdlib HTTP + WSGI create_app)
├── cli.py                   # `att` / `attachments` CLI
├── mcp_server.py            # `attachments-mcp` MCP server (att + att_options tools)
├── dsl.py                   # DSL parsing ("file.pdf[pages: 1-4]")
├── _options.py              # Option schemas: declare/resolve/export (att.options)
├── _help.py                 # att.help(): printed one-screen overview
├── types.py                 # Artifact / ImageItem TypedDicts, error codes, helpers
├── utils.py                 # Encoding detection, magic-byte detection, helpers
├── render.py                # Last mile: render_text, to_claude/openai_messages, chunk
├── _sources/                # Input resolution (WHERE files come from)
│   ├── __init__.py          # Source registry, @source decorator & unpack() dispatch
│   ├── _guards.py           # Security: expansion budget, sanitization, SSRF guard
│   ├── local.py             # Local files, glob patterns + deterministic directory walk
│   ├── archives.py          # ZIP/TAR expansion (recursive, bomb-guarded)
│   ├── http.py              # HTTP(S) single-file download
│   └── github.py            # github:// + github.com repo roots
└── _processors/
    ├── __init__.py          # Processor registry & @processor decorator
    ├── text.py              # Text files (no deps)
    ├── pdf.py               # PDF (pypdf, pymupdf)
    ├── xlsx.py              # Excel .xlsx (openpyxl, pandas) + legacy .xls (xlrd)
    ├── docx.py              # Word (python-docx)
    ├── html.py              # HTML, CSS select (beautifulsoup4, lxml)
    ├── pptx.py              # PowerPoint (python-pptx)
    ├── csv.py               # CSV/TSV tables (stdlib; optional pandas summary)
    ├── svg.py               # SVG/SVGZ text (stdlib; optional cairosvg raster)
    ├── image.py             # Images png/jpg/gif/webp/bmp/tiff/heic (Pillow, pillow-heif) + shared OCR layer (rapidocr)
    ├── ipynb.py             # Jupyter notebooks (stdlib json/base64; optional cell outputs)
    └── audio.py             # Audio transcription mp3/wav/m4a/flac/ogg/opus (faster-whisper)
```

---

## Testing Locally

```bash
# Install dev dependencies
uv sync --group dev

# Run tests
uv run pytest

# Run one file
uv run pytest tests/test_conformance.py

# Check linting
uv run ruff check src/
uv run ruff format src/

# Test zero-dep mode (fresh env)
uv venv --seed /tmp/test-env
/tmp/test-env/bin/pip install -e .
/tmp/test-env/bin/python -c "from attachments import att; print(att('README.md'))"
```

---

## Self-Hosted Server

One team member can set up a server with all dependencies, and everyone else connects to it.

### Architecture

```
┌──────────────────────────┐          ┌──────────────────────────────────┐
│ Client Machines          │          │ Server Machine                   │
│ (minimal deps)           │          │ (all deps installed)             │
│                          │          │                                  │
│ pip install              │   HTTP   │ pip install attachments[server]  │
│   attachments[service]   │ ──────>  │                                  │
│                          │          │ attachments-server               │
│ from attachments import  │          │   --host 0.0.0.0                 │
│   att, configure         │          │   --port 8000                    │
│                          │          │                                  │
│ configure(               │          │ ┌────────────────────────────┐   │
│   service_url="...",     │          │ │ All processors available:  │   │
│   api_key="..."          │          │ │ • pypdf, pymupdf (PDF)     │   │
│ )                        │          │ │ • openpyxl, pandas (Excel) │   │
│                          │          │ │ • python-docx (Word)       │   │
│ att("document.pdf")      │  <────   │ │ • bs4, lxml (HTML)         │   │
│ # Returns artifact!      │ artifact │ │ • ... everything shipped   │   │
└──────────────────────────┘          │ │                            │   │
                                      │ └────────────────────────────┘   │
                                      └──────────────────────────────────┘
```

### Server Setup (one machine with all deps)

```bash
# Install everything
pip install attachments[server]

# Set an API key for security
export ATTACHMENTS_SERVER_KEY="your-team-secret"

# Run the server
attachments-server --host 0.0.0.0 --port 8000

# Or with Python
python -m attachments.server --host 0.0.0.0 --port 8000
```

Output:
```
╔══════════════════════════════════════════════════════════════╗
║                   Attachments Server                         ║
╠══════════════════════════════════════════════════════════════╣
║  URL:  http://0.0.0.0:8000                                  ║
║  Auth: enabled                                              ║
╠══════════════════════════════════════════════════════════════╣
║  Endpoints:                                                  ║
║    POST /process  - Process a file                           ║
║    POST /unpack   - Unpack a URL                             ║
║    GET  /health   - Health check                             ║
║    GET  /formats  - List supported formats                   ║
║    GET  /options  - DSL option schemas                       ║
╚══════════════════════════════════════════════════════════════╝

Available features: pdf, pdf-text, pdf-images, xlsx, xlsx-pandas, docx, pptx, html, image, service
```

### Client Setup (zero deps needed)

```bash
# Clients only need httpx
pip install attachments[service]
```

```python
from attachments import att, configure

# Point to your team's server
configure(
    service_url="http://server-ip:8000",
    api_key="your-team-secret"
)

# Everything works - processed on server!
artifacts = att("document.pdf")
artifacts = att("spreadsheet.xlsx")
```

### Environment Variables

**Server:**
```bash
ATTACHMENTS_SERVER_KEY=secret    # API key (optional, but recommended)
ATTACHMENTS_MAX_UPLOAD=268435456 # Max upload size (default 256MB)
```

**Client:**
```bash
ATTACHMENTS_API_KEY=secret           # API key
ATTACHMENTS_SERVICE_URL=http://...   # Server URL
```

### Production Deployment

For production, use a proper WSGI server:

```bash
# With gunicorn
pip install gunicorn
gunicorn "attachments.server:create_app()" -b 0.0.0.0:8000 -w 4

# With Docker (example Dockerfile)
FROM python:3.12-slim
RUN pip install attachments[server] gunicorn
ENV ATTACHMENTS_SERVER_KEY=changeme
EXPOSE 8000
CMD ["gunicorn", "attachments.server:create_app()", "-b", "0.0.0.0:8000"]
```

### Use Cases

1. **Team Server**: One powerful machine processes files for the whole team
2. **CI/CD**: Server in your infrastructure, CI runners use service mode
3. **Serverless**: Clients in Lambda/Cloud Functions connect to a central server
4. **Air-gapped**: Server inside secure network, no external API calls

---

## Service Integration

When a local processor is missing an optional dependency, it returns the
**typed** missing-dependency artifact. Core routing checks the error *code*
(via `attachments.types.is_missing_dependency`) — never the error message —
and automatically tries the service when an API key is configured:

```python
# In your processor - return the typed missing-dep artifact.
# The core.py routing handles service fallback automatically.
from attachments import missing_dep_artifact


def my_processor(data: bytes, **options) -> dict:
    filename = options.get("filename", "file.myf")
    try:
        import mylib
    except ImportError:
        # code == "missing-dependency" — this (and only this) triggers
        # the local -> service fallback. The pip install hint comes from
        # deps.DEPENDENCY_MAP.
        return missing_dep_artifact(filename, "myformat")
    ...
```

Other error codes (`parse-error`, `password-required`, ...) are final: a
file that could not be parsed locally is not retried on the service in the
default `prefer="local"` mode. String-matching error messages is forbidden
by the IR contract (`spec/IR-CONTRACT.md`).

---

## Artifact Structure

All processors must return this structure (see `spec/IR-CONTRACT.md` for the
binding contract; build it with `attachments.make_artifact`):

```python
{
    "text": str,           # Extracted text content (may be "")
    "images": [            # List of images
        {
            "name": str,       # e.g., "doc-page-1.png"
            "mimetype": str,   # e.g., "image/png"
            "bytes": bytes,    # Raw image bytes (bytes_b64 on the wire)
            "page": int,       # Optional: source page number
        }
    ],
    "audio": [],           # Reserved for future
    "video": [],           # Reserved for future
    "meta": {              # Typed metadata envelope (optional keys ABSENT,
                           # never None)
        "source": str,     # Added automatically by core.py
        "kind": str,       # "text" | "pdf" | "table" | "document" | "html" | ...
        "via": str,        # "service" when processed remotely
        "error": {         # Present only on failure
            "code": str,       # e.g. "missing-dependency", "parse-error"
            "message": str,    # Human-readable, includes remedy when known
        },
        "note": str,       # Informational (e.g. "no processor available")
        "warnings": [str],     # Non-fatal warnings
        "segments": [dict],    # Structural segmentation (pages/sheets/...)
        "extra": dict,     # Processor-specific freeform metadata
    },
}
```

Error codes are constants in `attachments.types`:
`ERROR_MISSING_DEPENDENCY`, `ERROR_PASSWORD_REQUIRED`, `ERROR_PARSE`,
`ERROR_UNPACK`, `ERROR_SERVICE`, `ERROR_INVALID_OPTION`, `ERROR_PROCESSING`.

Helpers in `attachments.types` (also exported from `attachments`):

```python
make_artifact(text="", images=None, audio=None, video=None, meta=None)
error_artifact(source, code, message)
missing_dep_artifact(source, feature)   # looks up install hint from deps.py
is_missing_dependency(artifact)         # typed check used by core routing
normalize_artifact(artifact, source)    # fills required keys + meta.source
```
