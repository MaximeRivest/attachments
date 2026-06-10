# attachments

> Turn anything into LLM-ready artifacts.

`att("report.pdf")` → text + images you can put straight into a prompt. One
function, one output shape, any input. Zero required dependencies — install
format support as you need it, or let a service/server do the processing.

> 🧭 **This is attachments 1.0** — a complete rewrite that succeeds the 0.25.x
> series of the published [`attachments`](https://pypi.org/project/attachments/)
> package. Read [VISION.md](VISION.md) for where the project is going,
> [CHANGELOG.md](CHANGELOG.md) for what changed (and how to migrate), and
> [DEVELOPMENT.md](DEVELOPMENT.md) to add processors or sources.

## Quick Start

```bash
# Install core (text files work out of the box)
pip install attachments

# Add format support as needed
pip install attachments[pdf]         # PDF support
pip install attachments[xlsx]        # Excel support
pip install attachments[docx]        # Word support
pip install attachments[pptx]        # PowerPoint support
pip install attachments[html]        # HTML support
pip install attachments[image]       # png/jpg/gif/webp/bmp/tiff support
pip install attachments[service]     # API fallback mode
pip install attachments[clipboard]   # `att --copy` clipboard support
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

## Interactive Use

`att()` returns `Artifacts` — a `list` subclass of plain artifact dicts that
is a joy in a REPL or notebook. The repr is a one-line summary (it never
dumps text or bytes); errors get one `!` line each — capped at 10, the rest
collapse into a `+N more errors (see .errors)` line (real runs):

```python
>>> att("report.pdf[pages: 1-2, images: true]")
<Artifacts: 1 artifact | 94 chars | 2 images>

>>> att("missing.pdf")
<Artifacts: 1 artifact | 0 chars | 1 error>
  ! missing.pdf: unpack-error — unpack failed: Unsupported or non-existent input: missing.pdf
```

`print()` (or `.text`) gives the full assembled prompt — v1 muscle memory:

```python
>>> print(att("report.pdf[pages: 1-2]"))
## report.pdf
Hello from page 1. Quarterly revenue grew 12%.

Hello from page 2. Quarterly revenue grew 12%.
```

The last mile hangs right off the result (`prompt` is optional everywhere),
and `.images` / `.errors` flatten the parts you reach for most:

```python
a = att("report.pdf[pages: 1-2, images: true]")
a.claude("Summarize in one sentence.")  # Claude messages: [text, image, image, text]
a.openai("Summarize in one sentence.")  # OpenAI messages (data-URL image parts)
a.chunk(max_chars=4000)                 # segment-aware RAG chunks
a.images                                # flattened ImageItem dicts
a.errors                                # [{"source", "code", "message"}, ...]
a[:1] + a[1:]                           # slices/concat stay Artifacts; a[0] is a dict
```

In Jupyter, a bare `att("report.pdf[images: true]")` cell renders the summary,
error admonitions, a text preview, and up to 4 inline image thumbnails.

Discovery is built in: `att.options(".pdf")` pretty-prints the declared
option table (same data as before — `json.dumps` still works), and
`att.help()` prints a one-screen overview (real run):

```python
>>> att.options(".pdf")
Option     Type          Aliases  Default  Example           Description
pages      pages         page     —        pages: 1-4        Pages to include: a 1-based
                                                             page number or range.
password   str           pw       —        password: secret  Password for encrypted
                                                             PDFs.
images     bool_or_auto  render   "auto"   images: true      Render pages to PNG:
                                                             true/false, or auto (only
                                                             when no text).
dpi        int           —        200      dpi: 300          Resolution for rendered
                                                             page images.
max_pages  int           —        —        max_pages: 10     Hard cap on the number of
                                                             pages parsed/rendered.
```

Editors get the same delight statically: a generated typing stub
(`__init__.pyi`, built from the declared option schemas) autocompletes every
DSL option's kwarg twin — `att("doc.pdf", pages=` ⇥ — and types
`att.options` / `att.help`.

## The Artifact

Every input becomes a list of artifacts — the universal output shape every
processor produces and every consumer can rely on. A real run:

```python
>>> att("report.pdf")[0]
{
    "text": "Hello from page 1. Quarterly revenue grew 12%.\n\nHello from page 2. ...",
    "images": [],          # ImageItem dicts: {name, mimetype, bytes, page}
    "audio": [],           # Reserved
    "video": [],           # Reserved
    "meta": {
        "source": "report.pdf",
        "kind": "pdf",
        "segments": [      # Structural segmentation: offsets into text
            {"kind": "page", "label": "page 1", "start": 0, "end": 46},
            {"kind": "page", "label": "page 2", "start": 48, "end": 94},
            {"kind": "page", "label": "page 3", "start": 96, "end": 142},
        ],
        "extra": {"encrypted": False, "text_backend": "pypdf", "pages": 3, "parsed_pages": 3},
    },
}
```

`meta` is a **typed envelope**: optional keys (`kind`, `via`, `error`, `note`,
`warnings`, `segments`, `extra`) are absent when not applicable, never `None`.
Errors never raise out of `att()` — they come back as artifacts with a typed
`meta.error` (real runs):

```python
>>> att("broken.pdf")[0]["meta"]["error"]
{'code': 'parse-error', 'message': 'Failed to parse PDF: Stream has ended unexpectedly'}

>>> att("report.pdf")[0]["meta"]["error"]   # in an env without pypdf/pymupdf
{'code': 'missing-dependency',
 'message': "Processing 'report.pdf' requires optional dependencies for 'pdf' "
            "(missing: pypdf|PyPDF2, pymupdf). Install with: pip install attachments[pdf]"}
```

The error codes (`missing-dependency`, `password-required`, `parse-error`,
`unpack-error`, `service-error`, `invalid-option`, `processing-error`) are
constants in `attachments.types`. The full binding contract — shape, meta
envelope, wire format — is one page: [spec/IR-CONTRACT.md](spec/IR-CONTRACT.md)
(JSON Schema in [spec/artifact.schema.json](spec/artifact.schema.json)),
enforced by a conformance suite that validates every processor and server
response in CI.

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

# HTML options
att("page.html[select: h1]")            # Only matching CSS-selected elements

# Image options
att("photo.jpg[rotate: 90]")            # Rotate 90° counterclockwise

# GitHub options
att("github://org/repo[branch: main]")  # Specific branch
att("github://org/repo[ref: v1.0.0]")   # Tag

# Combine with URLs
att("https://arxiv.org/pdf/2301.00001.pdf[pages: 1-5]")
```

**Values:** numbers, booleans (`true`/`false`), ranges (`1-4`), bare or quoted
strings. The whole grammar (with shared parser test vectors every
implementation must pass) lives in [spec/dsl-grammar.md](spec/dsl-grammar.md).

**Keys belong to processors:** each processor declares its option schema
(with aliases like `page` → `pages`, `pw` → `password`, `branch` → `ref`),
and everything above resolves through those schemas. Discover them at
runtime — `att.options(".pdf")` lists one processor's options,
`att.options()` exports everything (also: `att --options` on the CLI,
`GET /options` on the server, and the generated cheatsheet in
[docs/dsl-options.md](docs/dsl-options.md)):

```python
>>> [o["name"] for o in att.options(".pdf")]
['pages', 'password', 'images', 'dpi', 'max_pages']
>>> att.options(".pdf")[0]
{'name': 'pages', 'type': 'pages', 'aliases': ['page'], 'param': None, 'default': None,
 'help': 'Pages to include: a 1-based page number or range.', 'example': 'pages: 1-4'}
```

Unknown keys never fail silently; they are dropped with a warning in that
artifact's `meta["warnings"]` (real run):

```python
>>> att("data.xlsx[sheets: 0]")[0]["meta"]["warnings"]
["Unknown option 'sheets' for .xlsx — did you mean 'sheet'?"]
```

Every DSL option has a keyword-argument twin, and explicit kwargs win:
`att("doc.pdf[pages: 1-4]")` ≡ `att("doc.pdf", pages="1-4")`, and
`att("doc.pdf[pages: 1-4]", pages="1-2")` processes pages 1–2.

## The Last Mile

`att()` returns `Artifacts`, a `list[Artifact]` subclass (see
[Interactive Use](#interactive-use)); `attachments.render` turns any artifact
list straight into prompts, API messages, or RAG chunks (all outputs below
are real runs — `prompt=` is optional in both adapters):

```python
from attachments import att, render_text, to_claude_messages, to_openai_messages, chunk

artifacts = att("report.pdf[pages: 1-2]")

# One prompt-ready string with ## <source> headers
print(render_text(artifacts))
# ## report.pdf
# Hello from page 1. Quarterly revenue grew 12%.
#
# Hello from page 2. Quarterly revenue grew 12%.

# Claude Messages API — plain dicts, no anthropic SDK import
to_claude_messages(artifacts, prompt="Summarize in one sentence.")
# [{'role': 'user', 'content': [
#     {'type': 'text', 'text': '## report.pdf\nHello from page 1. ...'},
#     {'type': 'text', 'text': 'Summarize in one sentence.'}]}]
# (images become {'type': 'image', 'source': {'type': 'base64', ...}} blocks)

# OpenAI Chat Completions — image parts become data: URLs
to_openai_messages(artifacts, prompt="Summarize in one sentence.")
# [{'role': 'user', 'content': [{'type': 'text', ...}, {'type': 'text', ...}]}]

# Deterministic, segment-aware chunking for RAG (pages are never split
# unless a single page alone exceeds max_chars)
chunk(att("report.pdf"), max_chars=100)
# ['## report.pdf\nHello from page 1. Quarterly revenue grew 12%.\n\nHello from page 2. ...',
#  '## report.pdf\nHello from page 3. Quarterly revenue grew 12%.']
```

## Magic-Byte Routing

When the extension lies or is missing, content detection routes anyway:

```python
>>> att("mystery_download")[0]["meta"]["kind"]   # no extension; bytes start with %PDF
'pdf'
```

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
│  - http(s)://   │         │  - .pptx        │
│  - github://    │         │  - .html        │
│                 │         │  - images       │
│                 │         │  - text (20+)   │
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
from attachments import processor, source, Option

@processor(".myf", options=(Option("depth", "int", help="Parse depth."),))
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

The fallback is driven by the typed `missing-dependency` error code, never by
string-matching error messages (see the IR contract).

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

Endpoints: `POST /process`, `POST /unpack`, `GET /health`, `GET /formats`,
`GET /options`. See [examples/self_hosted_server.md](examples/self_hosted_server.md)
for Docker, systemd, CI/CD, and the API reference.

## CLI

```bash
att report.pdf                  # Print extracted text
att "data.xlsx[sheet: Sales]"   # DSL works here too
att report.pdf --pages 1-4      # Unknown --key value becomes [key:value]
att . --json                    # Whole directory as JSON artifacts
att README.md --copy --prompt "Summarize this"   # To clipboard, prompt first
                                # (--copy needs: pip install attachments[clipboard])
att --options                   # Every declared DSL option
att --options .xlsx             # One processor's options
```

```text
$ att --options .xlsx
.xlsx
  sheet                    str_or_int   Sheet to render: a sheet name or 0-based index. Omit to render all sheets.  e.g. [sheet: Sales]
  rows (max_rows)          int          Maximum number of rows rendered as text per sheet.  e.g. [rows: 100]
```

## Status & Contributing

Shipped today: text (20+ extensions), PDF, XLSX, XLS, DOCX, PPTX, HTML
(with `select:` CSS extraction), CSV/TSV (real tables, optional pandas
summary), SVG (text extraction + optional raster), and image
(png/jpg/gif/webp/bmp/tiff/heic, with `rotate:`) processors; local files,
directories, glob patterns (`att("src/**/*.py")`), zip/tar, HTTP(S), and
`github://` sources; service client, self-hosted server, and CLI.
The last mile ships too: `render_text` / `to_claude_messages` /
`to_openai_messages` / `chunk` turn artifact lists straight into prompts,
API messages, or RAG chunks. The IR contract and DSL grammar are frozen in
[spec/](spec/) and enforced by a conformance suite; the generated option
cheatsheet lives in [docs/dsl-options.md](docs/dsl-options.md).

Everything else (legacy `.doc`/`.ppt`, EPS, OCR, audio, `s3://`,
`gdrive://`, `notion://`, …) is the
long tail we want help with — each new processor is one pure function
`(bytes, options) -> artifact` plus a declared option schema. Start with
[VISION.md](VISION.md), then [DEVELOPMENT.md](DEVELOPMENT.md) for the
step-by-step checklist and [CONTRIBUTING.md](CONTRIBUTING.md) for the
workflow.
