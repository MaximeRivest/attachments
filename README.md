# attachments

> Turn anything into LLM-ready artifacts.

`att("report.pdf")` → text + images you can put straight into a prompt. One
function, one output shape, any input. Zero required dependencies — install
format support as you need it, or let a service/server do the processing.

> 🧭 **This repo is the first stable major version (1.0) of the published
> [`attachments`](https://pypi.org/project/attachments/) package (currently
> 0.25.x).** Read [VISION.md](VISION.md) for where the project is going and the
> roadmap, and [DEVELOPMENT.md](DEVELOPMENT.md) to add processors or sources.

## Quick Start

```bash
# Install core (text files work out of the box)
pip install attachments

# Add format support as needed
pip install attachments[pdf]         # PDF support
pip install attachments[xlsx]        # Excel support
pip install attachments[docx]        # Word support
pip install attachments[html]        # HTML support
pip install attachments[service]     # API fallback mode
pip install attachments[all-local]   # Everything currently shipped
```

```python
from attachments import att, configure, check_deps

# See what's available
check_deps()  # {'pdf': True, 'xlsx': True, 'service': False, ...}

# Process anything
artifacts = att("document.pdf")
artifacts = att("data/")                    # Directory
artifacts = att("archive.zip")              # Archives (recursive)
artifacts = att("github://owner/repo")      # GitHub repo
artifacts = att("https://example.com/f.pdf") # URL

# Inline options with DSL syntax
artifacts = att("report.pdf[pages: 1-4]")
artifacts = att("report.pdf[pages: 1-10, images: true, dpi: 300]")
artifacts = att("data.xlsx[sheet: Sales, rows: 100]")
artifacts = att("github://org/repo[branch: develop]")

# With service fallback (when local deps missing)
configure(api_key="att_...")
artifacts = att("document.pdf")  # Uses service if pypdf not installed
```

## The Artifact

Every input becomes a list of artifacts — the universal output shape every
processor produces and every consumer can rely on:

```python
{
    "text": "...",      # What LLMs read
    "images": [...],    # What multimodal LLMs see
    "audio": [],        # Reserved
    "video": [],        # Reserved
    "meta": {...}       # Typed metadata: source, kind, error{code,message}, via
}
```

## DSL Syntax

Specify options inline with `[key: value, ...]`:

```python
# PDF options
att("doc.pdf[pages: 1-4]")              # Pages 1-4 (1-based)
att("doc.pdf[pages: 5-10, images: true]") # With image rendering
att("doc.pdf[dpi: 300]")                # High-res images
att("doc.pdf[password: secret]")        # Encrypted PDF

# Excel options
att("data.xlsx[sheet: Revenue]")        # Specific sheet
att("data.xlsx[sheet: 0, rows: 50]")    # First sheet, 50 rows

# GitHub options
att("github://org/repo[branch: main]")  # Specific branch
att("github://org/repo[ref: v1.0.0]")   # Tag

# Combine with URLs
att("https://arxiv.org/pdf/2301.00001.pdf[pages: 1-5]")
```

**Keys** belong to processors: each processor declares its option schema
(with aliases like `page` → `pages`, `pw` → `password`, `branch` → `ref`),
and everything above resolves through those schemas. Discover them at
runtime — `att.options(".pdf")` lists one processor's options,
`att.options()` lists everything (also: `att --options` on the CLI,
`GET /options` on the server). Unknown keys never fail silently; they are
dropped with a warning in that artifact's `meta["warnings"]`:

```python
att("data.xlsx[sheets: 0]")
# meta["warnings"] == ["Unknown option 'sheets' for .xlsx — did you mean 'sheet'?"]
```

**Values:** Numbers, booleans (`true`/`false`), ranges (`1-4`), strings

Every DSL option has a keyword-argument twin, and explicit kwargs win:
`att("doc.pdf[pages: 1-4]")` ≡ `att("doc.pdf", pages="1-4")`, and
`att("doc.pdf[pages: 1-4]", pages="1-2")` processes pages 1–2.

## Architecture

Two orthogonal registries connected by a universal intermediate representation:

```
┌─────────────────┐         ┌─────────────────┐
│  WHERE it comes │         │  WHAT it is     │
│  from           │         │                 │
│  unpack handlers│         │  processors     │
│  - local files  │         │  - .pdf         │
│  - directories  │         │  - .xlsx        │
│  - zip/tar      │         │  - .docx        │
│  - http(s)://   │         │  - .html        │
│  - github://    │         │  - text (20+)   │
└────────┬────────┘         └────────┬────────┘
         │                           │
         └──────────┬────────────────┘
                    ▼
              (filename, bytes)
                    │
                    ▼
               artifact
```

Source and format are decoupled: a PDF from GitHub uses the same processor as
a PDF from disk, and every new source multiplies with every format. Both
registries are open:

```python
from attachments import processor, source

@processor(".myf")
def myformat_processor(data: bytes, **options) -> dict: ...

@source("myproto://")
def myproto_handler(url: str) -> list[tuple[str, bytes]]: ...
```

## Local / Service Fallback

```python
att("file.pdf", prefer="local")
```

- `prefer="local"` (default): try local processors, fall back to service
- `prefer="service"`: try service first, fall back to local
- `prefer="local-only"`: only local, fail if deps missing
- `prefer="service-only"`: only service, requires API key

## Self-Hosted Server

Run your own server with all deps, let others connect with zero deps:

```bash
# On server (one machine, all deps):
pip install attachments[server]
export ATTACHMENTS_SERVER_KEY="team-secret"
attachments-server --host 0.0.0.0 --port 8000

# On clients (zero deps needed):
pip install attachments[service]
```

```python
from attachments import att, configure

configure(service_url="http://server:8000", api_key="team-secret")
att("document.pdf")  # Processed on server!
```

See [examples/self_hosted_server.md](examples/self_hosted_server.md) for
Docker, systemd, CI/CD, and API reference.

## CLI

```bash
att report.pdf                  # Print extracted text
att "data.xlsx[sheet: Sales]"   # DSL works here too
```

## Status & Contributing

Shipped today: text (20+ extensions), PDF, XLSX, DOCX, HTML, PPTX, and image
(png/jpg/gif/webp/bmp/tiff) processors; local files, directories, zip/tar,
HTTP(S), and `github://` sources; service client, self-hosted server, and CLI.
The last mile ships too: `render_text` / `to_claude_messages` /
`to_openai_messages` / `chunk` turn artifact lists straight into prompts,
API messages, or RAG chunks. Files with missing or wrong extensions are
routed by magic-byte content detection, so `att()` still does the right thing.

Everything else (OCR, audio, `s3://`, `gdrive://`, …) is the
long tail we want help with — each new processor is one pure function
`(bytes, options) -> artifact`. Start with [VISION.md](VISION.md), then
[DEVELOPMENT.md](DEVELOPMENT.md) for the step-by-step checklist.
