# attachments

> Turn anything into LLM-ready artifacts.

`att("report.pdf")` → text + images you can put straight into a prompt. One
function, one output shape, any input. Zero required dependencies — install
format support as you need it, or let a service/server do the processing.

> 🧭 **This is attachments 1.0** — a complete rewrite that succeeds the 0.25.x
> series of the published [`attachments`](https://pypi.org/project/attachments/)
> package. Start with the executed demo notebook
> [examples/demo.ipynb](https://github.com/maximerivest/attachments/blob/main/examples/demo.ipynb) and the launch post
> [ANNOUNCEMENT.md](https://github.com/maximerivest/attachments/blob/main/ANNOUNCEMENT.md). Migrating from 0.25.x?
> [docs/MIGRATION.md](https://github.com/maximerivest/attachments/blob/main/docs/MIGRATION.md) is the side-by-side guide. Read
> [VISION.md](https://github.com/maximerivest/attachments/blob/main/VISION.md) for where the project is going,
> [CHANGELOG.md](https://github.com/maximerivest/attachments/blob/main/CHANGELOG.md) for what changed, and
> [DEVELOPMENT.md](https://github.com/maximerivest/attachments/blob/main/DEVELOPMENT.md) to add processors or sources.

## Quick Start

```bash
# Install core (text files work out of the box).
# 1.0 is in beta: until 1.0.0 is out, a plain `pip install attachments`
# installs the old 0.25. The ">=1.0.0b1" below gets 1.0.
pip install "attachments>=1.0.0b1"

# Add format support as needed
pip install "attachments[pdf]>=1.0.0b1"        # PDF support
pip install "attachments[xlsx]>=1.0.0b1"       # Excel support
pip install "attachments[docx]>=1.0.0b1"       # Word support
pip install "attachments[pptx]>=1.0.0b1"       # PowerPoint support
pip install "attachments[html]>=1.0.0b1"       # HTML and web pages
pip install "attachments[browser]>=1.0.0b1"    # web page screenshots (then: playwright install chromium)
# .doc/.ppt/.odt/.odp/.ods: install LibreOffice (a program, not a pip package)
pip install "attachments[image]>=1.0.0b1"      # png/jpg/gif/webp/bmp/tiff support
pip install "attachments[ocr]>=1.0.0b3"        # OCR for scanned PDFs/images (large: pulls onnxruntime)
pip install "attachments[audio]>=1.0.0b1"      # mp3/wav/m4a/flac/ogg/opus transcription (large: pulls faster-whisper/ctranslate2)
pip install "attachments[service]>=1.0.0b1"    # API fallback mode
pip install "attachments[clipboard]>=1.0.0b1"  # `att --copy` clipboard support
pip install "attachments[all-local]>=1.0.0b1"  # Everything currently shipped (except ocr/audio — too big)
```

```python
from pathlib import Path

from attachments import att, configure, check_deps

# See what's available
check_deps()  # {'pdf': True, 'xlsx': True, 'service': False, ...}

# Process anything
artifacts = att("document.pdf")
artifacts = att("data/")                    # Folder: an overview, then the files
artifacts = att("reports/*/summary.md")     # Wildcards anywhere; ** for any depth
artifacts = att(["a.pdf", Path("b.csv")])   # Several inputs (str, Path, ~, file://)
artifacts = att("archive.zip")              # Archives (recursive)
artifacts = att("github://owner/repo")      # GitHub repo
artifacts = att("https://example.com/f.pdf") # URL

# Inline options with DSL syntax
artifacts = att("report.pdf[pages: 1-4]")
artifacts = att("report.pdf[pages: 1-10, images: true, dpi: 300]")
artifacts = att("data.xlsx[sheet: Sales, rows: 100]")
artifacts = att("scan.pdf[ocr: true]")      # OCR every scanned page (auto: the first 50)
artifacts = att("meeting.mp3[model: small, language: en]")  # audio transcription
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
<Artifacts: 1 artifact | 94 chars | ~8.1k tokens (images ~8.1k) | 2 images>

>>> att("missing.pdf")
<Artifacts: 1 artifact | 0 chars | ~0 tokens | 1 error>
  ! missing.pdf: unpack-error — unpack failed: Unsupported or non-existent input: missing.pdf
```

The `~N tokens` segment (also `.tokens`, split out by
`.estimate_tokens()` → `{'text': 24, 'images': 8064, 'total': 8088}`) is a
rough budget figure, not a tokenizer count: text is characters / 4, and each
image is Claude's count of 28 × 28 pixel patches after its resizing, on the
high-resolution tier of Claude 4.7 and later (up to 4,784 a picture), so a
budget holds for every Claude model; `.estimate_tokens(tier="standard")`
counts for other Claude models (up to 1,568; 2,992 here). OpenAI counts
differently. Image sizes are read from the file headers, with no extra
dependency.

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
a.parts()                               # neutral parts, page by page: [text, image, text, image]
a.claude("Summarize in one sentence.")  # Claude messages: [text, image, text, image, text]
a.openai("Summarize in one sentence.")  # OpenAI messages (data-URL image parts)
a.chunk(max_chars=4000)                 # segment-aware RAG chunks
a.images                                # flattened ImageItem dicts
a.errors                                # [{"source", "code", "message"}, ...]
a.raise_for_errors()                    # AttachmentsError if anything failed; returns a
a.to_wire()                             # JSON-ready list; Artifacts.from_wire() reverses it
a[:1] + a[1:]                           # slices/concat stay Artifacts; a[0] is a dict
```

Each page's text is followed by that page's image, so the model never has to
match page 7's picture to page 7's words by itself (`interleave=False` gives
the old layout: all text, then all images).

**Hiding file names.** Text starts each file with `## <name>`, and a picture
reads `[image: <name>]` — useful for a folder of documents, but a giveaway
when the task is "which animal is this?". `sources=False` works everywhere
(`to_text`, `parts`, `claude`, `openai`, `chunk`) (real run):

```python
>>> c = att("tabby_cat.png")
>>> c.text, c.to_text(sources=False)
('## tabby_cat.png\n[image: tabby_cat.png]', '[image]')
>>> [p["type"] for p in c.parts(sources=False)]   # no name anywhere
['image']
```

**Saving results.** Images hold raw bytes, which JSON cannot carry, so
`json.dumps(a)` fails as soon as there is an image. `a.to_wire()` returns the
wire form the server uses (images as base64 `bytes_b64`, valid against
[spec/artifact.schema.json](https://github.com/maximerivest/attachments/blob/main/spec/artifact.schema.json)), and never modifies
`a`:

```python
import json
from attachments import Artifacts

json.dump(a.to_wire(), open("report.json", "w"))
b = Artifacts.from_wire(json.load(open("report.json")))
assert b == a
```

In Jupyter, a bare `att("report.pdf[images: true]")` cell renders the summary,
error admonitions, a text preview, and up to 4 inline image thumbnails.

Discovery is built in: `att.options(".pdf")` pretty-prints the declared
option table (same data as before — `json.dumps` still works), and
`att.help()` prints a one-screen overview (real run):

```python
>>> att.options(".pdf")
Option        Type          Aliases  Default     Example              Description
pages         pages         page     —           pages: 1-4           Pages to read: 3,
                                                                      2-5, 7- (to the
                                                                      end), 1,3,5, -1
                                                                      (last), -3- (last
                                                                      three)
password      str           pw       —           password: secret     Password for
                                                                      encrypted PDFs.
images        bool_or_auto  render   "auto"      images: true         Pictures of pages:
                                                                      true/false, or auto
                                                                      (the pages with no
                                                                      text layer, such as
                                                                      scans).
dpi           int           —        200         dpi: 300             Resolution for
                                                                      rendered page images
                                                                      (max_dim caps the
                                                                      result).
max_dim       int           —        2000        max_dim: 1568        Longest side of each
                                                                      page image in
                                                                      pixels, applied
                                                                      after dpi; 0 = no
                                                                      cap.
image_format  str           —        "auto"      image_format: jpeg   auto (jpeg for
                                                                      scanned and photo
                                                                      pages, png for the
                                                                      rest), png
                                                                      (lossless, sharpest
                                                                      text) or jpeg (far
                                                                      smaller for scans).
quality       int           —        85          quality: 75          JPEG quality, 1-95
                                                                      (used with
                                                                      image_format: jpeg).
ocr           bool_or_auto  —        "auto"      ocr: true            Read pages with no
                                                                      text layer (scans)
                                                                      with RapidOCR:
                                                                      true/false, or auto
                                                                      (when rapidocr is
                                                                      installed; first 50
                                                                      such pages).
ocr_engine    str           —        "rapidocr"  ocr_engine: lighton  OCR engine: rapidocr
                                                                      (local, default) or
                                                                      lighton (remote
                                                                      LightOnOCR vLLM
                                                                      endpoint via ATTACHM
                                                                      ENTS_LIGHTON_URL).
max_pages     int           —        —           max_pages: 10        Hard cap on the
                                                                      number of pages
                                                                      parsed/rendered.
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
            {"kind": "page", "label": "page 1", "start": 0, "end": 46, "page": 1},
            {"kind": "page", "label": "page 2", "start": 48, "end": 94, "page": 2},
            {"kind": "page", "label": "page 3", "start": 96, "end": 142, "page": 3},
        ],
        "extra": {"encrypted": False, "text_backend": "pypdf", "pages": 3, "parsed_pages": 3},
    },
}
```

`meta` is a **typed envelope**: optional keys (`kind`, `via`, `error`, `note`,
`warnings`, `segments`, `extra`) are absent when not applicable, never `None`.
Errors never raise out of `att()` — they come back as artifacts with a typed
`meta.error`, so one broken file never sinks a folder of 100 (real runs):

```python
>>> att("broken.pdf")[0]["meta"]["error"]
{'code': 'parse-error', 'message': 'Failed to parse PDF: Stream has ended unexpectedly'}

>>> att("report.pdf")[0]["meta"]["error"]   # in an env without pypdf/pymupdf
{'code': 'missing-dependency',
 'message': "Processing 'report.pdf' requires optional dependencies for 'pdf' "
            "(missing: pypdf|PyPDF2, pymupdf). Install with: pip install attachments[pdf]"}
```

When a failure must stop the program instead (a missing file would otherwise
reach the model as an empty document), chain `raise_for_errors()`. Every file
is still processed; one exception then lists all failures and carries the
whole result (real run):

```python
>>> att("missing.pdf").raise_for_errors()
AttachmentsError: missing.pdf: unpack-error — unpack failed: Unsupported or non-existent input: missing.pdf
>>> # e.errors: same dicts as .errors; e.artifacts: everything, the good files too
```

A file type with no processor is not an error (an empty artifact with a
`meta.note`), so check the text or parts too if empty input must stop you.

The error codes (`missing-dependency`, `password-required`, `parse-error`,
`unpack-error`, `service-error`, `invalid-option`, `processing-error`) are
constants in `attachments.types`. The full binding contract — shape, meta
envelope, wire format — is one page: [spec/IR-CONTRACT.md](https://github.com/maximerivest/attachments/blob/main/spec/IR-CONTRACT.md)
(JSON Schema in [spec/artifact.schema.json](https://github.com/maximerivest/attachments/blob/main/spec/artifact.schema.json)),
enforced by a conformance suite that validates every processor and server
response in CI.

## DSL Syntax

Specify options inline with `[key: value, ...]`:

```python
# PDF options
att("doc.pdf[pages: 1-4]")              # Pages 1-4 (1-based)
att("doc.pdf[pages: 1,3,-1]")           # Pages 1 and 3, and the last page
att("doc.pdf[pages: 5-10, images: true]") # With image rendering
att("doc.pdf[dpi: 300]")                # High-res images (max_dim still caps them)
att("doc.pdf[images: true, max_dim: 1568, image_format: jpeg]")  # Smaller page images
att("doc.pdf[password: secret]")        # Encrypted PDF

# Excel options
att("data.xlsx[sheet: Revenue]")        # Specific sheet
att("data.xlsx[sheet: 0, rows: 50]")    # First sheet, 50 rows

# Web pages and HTML: Markdown of the main content (tables, code, maths)
att("https://example.com/article")      # Main content only (no menus, footers)
att("page.html[select: h1]")            # Only matching CSS-selected elements
att("https://example.com[main: false]") # The whole page, navigation included
att("https://example.com[links: true]") # Keep link addresses: [text](url)
att("https://example.com[screenshot: true, max_screens: 2]")  # + 1280x800 screenshots

# Image options
att("photo.jpg[rotate: 90]")            # Rotate 90° clockwise (photos are upright first)

# Word, PowerPoint, Excel: pictures drawn by LibreOffice
att("deck.pptx[pages: 2-4, images: true]")  # Slides 2-4, a picture of each
att("report.docx[images: auto]")        # Page pictures if LibreOffice is installed
att("deck.pptx[embedded_images: true]") # The pictures stored in the slides

# Folders, patterns, repos and archives (att.options("file://"))
att("repo/[files: false]")              # Overview only: tree, git, what was skipped
att("repo/[glob: '*.py, *.md']")        # Only matching files
att('repo/[ignore: "tests/, !uv.lock"]')# Skip more; ! brings a skipped file back
att("repo/[hidden: true]")              # Include dot files (.github/, ...)
att("repo/[max_files: 0, max_size: 0]") # No limits (default 1000 files, 256 MiB)
att("repo/[tree: false]")               # Files only, no overview

# GitHub options
att("github://org/repo[branch: main]")  # Specific branch
att("github://org/repo[ref: v1.0.0]")   # Tag

# Combine with URLs
att("https://arxiv.org/pdf/2301.00001.pdf[pages: 1-5]")
```

### Folders

A folder is read like a careful colleague would hand it over:

- **Skipped by default**: secrets (`.env`, private keys, credential files),
  dependencies and generated files (`node_modules`, virtual environments,
  caches, lock files, compiled and minified files), hidden files, and
  whatever `.gitignore` / `.attachmentsignore` exclude (full git rules,
  parent folders included). A single file you name is always read.
- **Limits**: 1000 files and 256 MiB by default; the overview says when
  reading stopped and how to go further.
- **Overview first**: the file tree, the git branch and commit, and what was
  skipped and why. `sources=False` leaves it out (it is made of names).
- Links leading outside the folder are never followed.

### Files a prompt mentions

```python
a = att.from_prompt("Compare `q3/report.pdf[pages: 1-3]` with data.csv")
a.claude("Compare the report with the data")
```

Mentions are looked up in the current folder (or `root=`) and never outside
it; secrets are never attached; URLs only with `urls=True` (a prompt's
author should not pick what your server fetches).

**Values:** numbers, booleans (`true`/`false`), ranges (`1-4`), bare or quoted
strings. The whole grammar (with shared parser test vectors every
implementation must pass) lives in [spec/dsl-grammar.md](https://github.com/maximerivest/attachments/blob/main/spec/dsl-grammar.md).

**Keys belong to processors:** each processor declares its option schema
(with aliases like `page` → `pages`, `pw` → `password`, `branch` → `ref`),
and everything above resolves through those schemas. Discover them at
runtime — `att.options(".pdf")` lists one processor's options,
`att.options()` exports everything (also: `att --options` on the CLI,
`GET /options` on the server, and the generated cheatsheet in
[docs/dsl-options.md](https://github.com/maximerivest/attachments/blob/main/docs/dsl-options.md)):

```python
>>> [o["name"] for o in att.options(".pdf")]
['pages', 'password', 'images', 'dpi', 'max_dim', 'image_format', 'quality', 'ocr', 'ocr_engine', 'max_pages']
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
from attachments import att, render_text, to_parts, to_claude_messages, to_openai_messages, chunk

artifacts = att("report.pdf[pages: 1-2]")

# One prompt-ready string with ## <source> headers
print(render_text(artifacts))
# ## report.pdf
# Hello from page 1. Quarterly revenue grew 12%.
#
# Hello from page 2. Quarterly revenue grew 12%.

# Provider-neutral parts: each page's text, then that page's images
to_parts(att("report.pdf[pages: 1-2, images: true]"))
# [{'type': 'text', 'text': '## report.pdf\nHello from page 1. Quarterly revenue grew 12%.'},
#  {'type': 'image', 'media_type': 'image/png', 'data': '<base64>'},
#  {'type': 'text', 'text': 'Hello from page 2. Quarterly revenue grew 12%.'},
#  {'type': 'image', 'media_type': 'image/png', 'data': '<base64>'}]

# Claude Messages API — plain dicts, no anthropic SDK import (built from to_parts)
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

A request a provider would reject (over Claude's 32 MB, too many pictures,
pictures too large, a format it does not take) gives a
`RequestLimitWarning` when it is built, naming the problem and the fix.

### Scanned documents

With `pip install "attachments[ocr]>=1.0.0b3"`, PDF pages that have no text
layer are read with OCR, page by page: a scanned PDF, or the two scanned
pages of an otherwise typed one. Those pages also come with their picture,
as JPEG (about 0.4 MB a page, so a 20-page scan is a 10 MB Claude request).
OCR runs locally, offline, several pages at once, with a progress bar on a
terminal or in a notebook; sideways and upside-down pages are turned upright
(their pictures too), and two-column pages are read column by column.

```python
att("scan.pdf")                 # text of up to 50 scanned pages, plus their pictures
att("scan.pdf[ocr: true]")      # every scanned page, however many
att("scan.pdf[ocr: false]")     # pictures only
configure(ocr_workers=1)        # one page at a time (each page read holds ~0.6 GB)
configure(ocr_max_pages=25)     # a server: no document reads more, even with ocr: true
```

On realistic test scans (English, French, invoices) under 0.5% of words
are wrong, at about 1 s a page on a desktop and 2 s on 2 cores:
[evals/scans](https://github.com/maximerivest/attachments/blob/main/evals/scans/README.md).

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
pip install "attachments[server]>=1.0.0b1"
export ATTACHMENTS_SERVER_KEY="team-secret"
attachments-server --host 0.0.0.0 --port 8000

# On clients (zero deps needed):
pip install "attachments[service]>=1.0.0b1"
```

```python
from attachments import att, configure

configure(service_url="http://server:8000", api_key="team-secret")
att("document.pdf")  # Processed on server!
```

Endpoints: `POST /process`, `POST /unpack`, `GET /health`, `GET /formats`,
`GET /options`. See [examples/self_hosted_server.md](https://github.com/maximerivest/attachments/blob/main/examples/self_hosted_server.md)
for Docker, systemd, CI/CD, and the API reference.

## CLI

```bash
att report.pdf                  # Print extracted text
att "data.xlsx[sheet: Sales]"   # DSL works here too
att report.pdf --pages 1-4      # Any --option value is a DSL option
att src --max-files 50 --glob '*.py'  # Flags combine (and with [..] in the path)
att . --json                    # Whole directory as JSON artifacts
att README.md --copy --prompt "Summarize this"   # To clipboard, prompt first
                                # (--copy needs: pip install "attachments[clipboard]>=1.0.0b1")
att --options                   # Every declared DSL option
att --options .xlsx             # One processor's options
```

```text
$ att --options .xlsx
.xlsx
  sheet                    str_or_int   Sheet to render: a sheet name or 0-based index. Omit to render all sheets.  e.g. [sheet: Sales]
  rows (max_rows)          int          Maximum number of rows rendered as text per sheet.  e.g. [rows: 100]
```

## Coding Agents (Skill)

attachments ships a skill that teaches coding agents (Claude Code, Pi,
Codex) to write code with it: installing 1.0 rather than 0.25, the options
that matter, sending files to Claude or OpenAI, hiding file names, stopping
on unreadable files, request-size limits, caching. Every example in it runs
in CI.

```bash
att --skill --install                      # every agent found: Claude Code, Pi, Codex
att --skill                                # where it is; who has it, up to date or not
att --skill --install .claude/skills       # one project only
uvx --from "attachments>=1.0.0b1" att --skill --install   # without installing it first
```

Re-run `att --skill --install` after upgrading to update the copies; a
skills folder that is a link (a checkout) is left alone. Whether it helps,
measured with fresh agents: [evals/skill/README.md](https://github.com/maximerivest/attachments/blob/main/evals/skill/README.md).

## Agents (MCP)

The same one-call ingestion, as an MCP server: any MCP-capable agent gets
an `att` tool (files, directories, globs, zip/tar, URLs, `github://` —
text plus page/slide images, with errors returned as readable text, never
exceptions) and an `att_options` tool to discover per-format options.

Claude Code:

```bash
claude mcp add attachments -- uvx --from "attachments[mcp]>=1.0.0b2" attachments-mcp
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "attachments": {
      "command": "uvx",
      "args": ["--from", "attachments[mcp]>=1.0.0b2", "attachments-mcp"]
    }
  }
}
```

Set `ATTACHMENTS_SERVICE_URL` (and `ATTACHMENTS_API_KEY`) in the server's
environment for hosted-tier OCR/audio without local optional installs.
Note: the server reads local files and fetches URLs with your permissions —
only attach it to agents you trust.

## Status & Contributing

Shipped today: text (20+ extensions), PDF (with OCR for scanned pages),
XLSX, XLS, DOCX, PPTX, HTML and web pages (Markdown of the main content,
`select:` CSS extraction, optional browser screenshots), CSV/TSV
(real tables, optional pandas summary), SVG (text extraction + optional
raster), image (png/jpg/gif/webp/bmp/tiff/heic, with `rotate:` and
`ocr:`), Jupyter notebook (`.ipynb`, zero-dep, optional cell outputs),
audio transcription
(mp3/wav/m4a/flac/ogg/opus via faster-whisper), and old Office /
OpenDocument files (`.doc`, `.ppt`, `.odt`, `.odp`, `.ods`, through
LibreOffice) processors; local files (`~`, `file://`), folders with skip
rules and limits, wildcard patterns (`att("src/**/*.py")`), lists of
inputs, zip/tar, HTTP(S), and `github://` sources; `att.from_prompt`;
service client, self-hosted server, and CLI.
The last mile ships too: `render_text` / `to_claude_messages` /
`to_openai_messages` / `chunk` turn artifact lists straight into prompts,
API messages, or RAG chunks. The IR contract and DSL grammar are frozen in
[spec/](https://github.com/maximerivest/attachments/tree/main/spec/) and enforced by a conformance suite; the generated option
cheatsheet lives in [docs/dsl-options.md](https://github.com/maximerivest/attachments/blob/main/docs/dsl-options.md).

Everything else (EPS, video, `s3://`,
`gdrive://`, `notion://`, …) is the
long tail we want help with — each new processor is one pure function
`(bytes, options) -> artifact` plus a declared option schema. Start with
[VISION.md](https://github.com/maximerivest/attachments/blob/main/VISION.md), then [DEVELOPMENT.md](https://github.com/maximerivest/attachments/blob/main/DEVELOPMENT.md) for the
step-by-step checklist and [CONTRIBUTING.md](https://github.com/maximerivest/attachments/blob/main/CONTRIBUTING.md) for the
workflow.
