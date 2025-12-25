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
pip install attachments[service]     # Add service mode (httpx)
pip install attachments[office]      # xlsx + docx + pptx
pip install attachments[cloud]       # s3 + gcs + gdrive
pip install attachments[all-local]   # Everything local
```

---

## Building New Processors

Processors convert file bytes into artifacts. Each processor handles one or more file extensions.

### Quick Start (Decorator Pattern)

```python
# my_processors.py
from attachments import processor

@processor(".docx", ".doc")
def word_processor(data: bytes, **options) -> dict:
    """Process Word documents."""
    try:
        from docx import Document
    except ImportError:
        return {
            "text": "",
            "images": [],
            "audio": [],
            "video": [],
            "flags": {"error": "python-docx not installed"}
        }

    # ... process document ...
    return {
        "text": extracted_text,
        "images": [],
        "audio": [],
        "video": [],
        "flags": {"kind": "document"}
    }
```

That's it! The decorator registers it automatically.

### Alternative: Function Call

```python
from attachments import register_processor

def my_processor(data: bytes, **options) -> dict:
    ...

register_processor(".myf", my_processor)
```

### Full Example

Create `src/attachments/processors/myformat.py`:

```python
"""Processor for MyFormat files (.myf)."""

from __future__ import annotations

from typing import Any

from . import processor  # Use the decorator


@processor(".myf", ".myformat")
def myformat_processor(data: bytes, **options: Any) -> dict[str, Any]:
    """Convert MyFormat bytes to an artifact.

    Args:
        data: Raw file bytes
        **options: Processing options (filename, custom options, etc.)

    Returns:
        Artifact dict with text, images, audio, video, flags
    """
    filename = options.get("filename", "unknown")

    # Try to import the optional dependency
    try:
        import myformat_lib
    except ImportError:
        # Return error artifact - service will handle it
        return {
            "text": "",
            "images": [],
            "audio": [],
            "video": [],
            "flags": {
                "error": "myformat requires myformat-lib. "
                         "Install with: pip install attachments[myformat]",
                "filename": filename,
            },
        }

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

        return {
            "text": text,
            "images": images,
            "audio": [],
            "video": [],
            "flags": {
                "kind": "myformat",
                "filename": filename,
                "version": parsed.version,
            },
        }
    except Exception as e:
        return {
            "text": "",
            "images": [],
            "audio": [],
            "video": [],
            "flags": {
                "error": f"Failed to parse MyFormat: {e}",
                "filename": filename,
            },
        }


# Register for file extensions
register_processor(".myf", myformat_processor)
register_processor(".myformat", myformat_processor)
```

### Step 2: Import in `processors/__init__.py`

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
all-processors = [
    "attachments[pdf,pdf-fallback,xlsx-pandas,docx,pptx,html,image,myformat]",
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
from attachments import att, check_dep


def test_myformat_missing_dep():
    """Test graceful handling when myformat-lib not installed."""
    if check_dep("myformat").available:
        pytest.skip("myformat-lib is installed")

    # Should return error artifact, not raise
    result = att("test.myf")
    assert "error" in result[0]["flags"]
    assert "myformat" in result[0]["flags"]["error"]


@pytest.mark.skipif(
    not check_dep("myformat").available,
    reason="myformat-lib not installed"
)
def test_myformat_processing():
    """Test actual processing when dep is available."""
    # Create test file or use fixture
    result = att("tests/fixtures/sample.myf")
    assert result[0]["text"]
    assert result[0]["flags"]["kind"] == "myformat"
```

---

## Building New Source Handlers

Source handlers resolve input strings (URLs, paths, schemes) into `(filename, bytes)` pairs.

### Quick Start (Decorator Pattern)

```python
# my_sources.py
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

### Alternative: Function Call

```python
from attachments import register_unpack_handler

def my_handler(url: str) -> list[tuple[str, bytes]]:
    ...

register_unpack_handler("myproto://", my_handler)
```

### Full Example

Create `src/attachments/unpack/s3.py`:

```python
"""S3 source handler for attachments."""

from __future__ import annotations


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

Option A: **Auto-register in `unpack/__init__.py`** (for built-in handlers):

```python
# At module level, try to register if deps available
try:
    from .s3 import s3_handler
    from ..unpack import register_unpack_handler
    register_unpack_handler("s3://", s3_handler)
except ImportError:
    pass  # boto3 not installed, skip registration
```

Option B: **Lazy registration in main `unpack.py`** (preferred for optional deps):

```python
def unpack(input: str, extra_handlers=None) -> list[tuple[str, bytes]]:
    # ... existing code ...

    # S3 handling
    if input.startswith("s3://"):
        try:
            from .unpack.s3 import s3_handler
            return s3_handler(input)
        except ImportError:
            raise ImportError(
                "S3 support requires boto3. "
                "Install with: pip install attachments[s3]"
            )
```

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
    assert "error" in result[0]["flags"]


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
- [ ] **4. Add import** to `__init__.py` if needed
- [ ] **5. Update bundles** in pyproject.toml (`all-processors`, `cloud`, etc.)
- [ ] **6. Add tests** for both missing-dep and installed cases
- [ ] **7. Update dev dependencies** if needed for testing

### Dependency Naming Conventions

```toml
[project.optional-dependencies]
# Processors: named after format
pdf = [...]
xlsx = [...]
docx = [...]

# Processors with alternatives: use descriptive suffix
pdf-fallback = ["pdfminer.six"]      # Alternative backend
xlsx-pandas = ["pandas", "openpyxl"]  # Enhanced version

# Sources: named after service/protocol
s3 = [...]
gcs = [...]
gdrive = [...]

# Bundles: descriptive groupings
office = ["attachments[xlsx,docx,pptx]"]
cloud = ["attachments[s3,gcs,gdrive]"]
all-processors = [...]
all-sources = [...]
all-local = [...]

# Service mode
service = ["httpx"]
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
├── core.py                  # Main att() function, routing logic
├── config.py                # Global configuration
├── deps.py                  # Dependency detection
├── service.py               # Remote API client
├── utils.py                 # Encoding detection, helpers
├── unpack.py                # Input resolution (local, http, github)
└── processors/
    ├── __init__.py          # Processor registry
    ├── text.py              # Text files (no deps)
    ├── pdf.py               # PDF (pypdf, pymupdf)
    └── xlsx.py              # Excel (openpyxl, pandas)
```

---

## Testing Locally

```bash
# Install dev dependencies
uv sync --group dev

# Run tests
uv run pytest

# Run with specific optional deps
uv run --extra pdf pytest tests/test_pdf.py

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
│ att("document.pdf")      │  <────   │ │ • python-pptx (PowerPoint) │   │
│ # Returns artifact!      │ artifact │ │ • whisper (Audio)          │   │
│                          │          │ │ • tesseract (OCR)          │   │
└──────────────────────────┘          │ │ • ... everything else      │   │
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
║  URL:  http://0.0.0.0:8000                                   ║
║  Auth: enabled                                               ║
╠══════════════════════════════════════════════════════════════╣
║  Endpoints:                                                  ║
║    POST /process  - Process a file                           ║
║    POST /unpack   - Unpack a URL                             ║
║    GET  /health   - Health check                             ║
║    GET  /formats  - List supported formats                   ║
╚══════════════════════════════════════════════════════════════╝

Available features: pdf, pdf-text, pdf-images, xlsx, xlsx-pandas, docx, ...
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
artifacts = att("presentation.pptx")
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

When local processing fails or isn't available, the library can fall back to a remote service:

```python
# In your processor - just return error artifact
# The core.py routing will handle service fallback automatically

def my_processor(data: bytes, **options) -> dict:
    try:
        import mylib
    except ImportError:
        return {
            "text": "",
            "images": [],
            "audio": [],
            "video": [],
            "flags": {
                "error": "mylib not installed",  # This triggers fallback
            },
        }
```

The `core.py` checks for error patterns like "not installed", "requires", "ImportError" and automatically tries the service if an API key is configured.

---

## Artifact Structure

All processors must return this structure:

```python
{
    "text": str,           # Extracted text content
    "images": [            # List of images
        {
            "name": str,       # e.g., "doc-page-1.png"
            "mimetype": str,   # e.g., "image/png"
            "bytes": bytes,    # Raw image bytes
            "page": int,       # Optional: source page number
        }
    ],
    "audio": [],           # Reserved for future
    "video": [],           # Reserved for future
    "flags": {             # Metadata
        "source": str,     # Added automatically by core.py
        "kind": str,       # Optional: "pdf", "table", "document"
        "error": str,      # If processing failed
        # ... processor-specific metadata
    },
}
```
