# Upgrading from attachments 0.25 to 1.0

1.0 is a complete rewrite. One function, `att()`, returns one frozen output
shape; the `load | modify | present | refine | adapt` grammar is gone. Most
everyday code is a rename — but several **defaults changed**, so read
[What behaves differently](#what-behaves-differently) even if your code still
runs.

The 0.25 line stays on PyPI (bug fixes only). Pin `attachments<1` to keep it
while you migrate.

**Contents:** [Before you upgrade](#before-you-upgrade) ·
[Your code, line by line](#your-code-line-by-line) ·
[What behaves differently](#what-behaves-differently) ·
[Options: 0.25 → 1.0](#options-025--10) ·
[Formats and sources](#formats-and-sources) ·
[New in 1.0](#new-in-10) ·
[Gone, and what to do instead](#gone-and-what-to-do-instead)

---

## Before you upgrade

| | 0.25 | 1.0 |
|---|---|---|
| Install | `pip install attachments` | `pip install "attachments[pdf,docx,image]>=1.0.0b1"` (while 1.0 is in beta, a plain `pip install attachments` still gets 0.25) |
| Python | 3.10+ | **3.11+** (3.10 ends its life in October 2026) |
| Always-installed packages | 12 (requests, beautifulsoup4, pillow, pydantic, pdfplumber, pillow-heif, nbformat, copykitten, typer, pyperclip, pytesseract, pypdfium2) | **none** — install the formats you use as extras |
| OCR | Tesseract (a program to install) via pytesseract | RapidOCR, a pip extra: `attachments[ocr]` |
| Web pages | needed Playwright + Chromium for every page | plain download; Chromium only for opt-in screenshots: `attachments[browser]` |
| `.doc`, `.ppt`, ... | — | LibreOffice (a program, not a pip extra) |

**Extras:** `pdf`, `docx`, `xlsx`, `pptx`, `html`, `image`, `heic`, `svg`,
`xls`, `csv-pandas`, `ocr`, `audio`, `browser`, `clipboard`, `mcp`, `service`,
and the bundles `office` (xlsx + docx + pptx), `all-local` (every format
except the large `ocr`/`audio`) and `server`. You don't need to guess: a file
whose extra is missing comes back as an error artifact with the exact
`pip install` command.

---

## Your code, line by line

| 0.25 | 1.0 |
|---|---|
| `from attachments import Attachments` | `from attachments import att` |
| `ctx = Attachments("report.pdf")` | `a = att("report.pdf")` |
| `Attachments("a.pdf", "b.csv")` / `Attachments([...])` | `att(["a.pdf", "b.csv"])` (or `att("a.pdf") + att("b.csv")`); `pathlib.Path`, `~` and `file://` work too |
| `str(ctx)` / `f"{ctx}"` | `str(a)` / `print(a)` / `a.text` |
| `ctx.images` (base64 data-URL strings) | `a.images` — dicts `{name, mimetype, bytes, page}`; raw base64: `base64.b64encode(img["bytes"]).decode()` |
| `ctx.metadata` | each artifact's `meta`: `a[0]["meta"]` (`kind`, `segments`, `extra`, `warnings`, `error`) |
| `ctx[0]` (an `Attachment` object) | `a[0]` — a plain dict ([spec/IR-CONTRACT.md](../spec/IR-CONTRACT.md)) |
| `ctx.claude("prompt")` | `a.claude("prompt")` |
| `ctx.openai_chat("prompt")` / `ctx.openai(...)` | `a.openai("prompt")` (Chat Completions) |
| `ctx.openai_responses("prompt")` | map `a.parts()` — [example below](#openai-responses-api) |
| `auto_attach(prompt, root_dir=...)` | `att.from_prompt(prompt, root=...)`, then `.claude(prompt)` — web addresses need `urls=True` |
| `from attachments.dspy import Attachments` | not ported: pass `a.text` and `a.images` to your DSPy signature |
| `ctx.agno(...)`, clipboard adapters | not ported (CLI: `att file --copy`) |
| `attach("doc.pdf") \| load.x \| present.y \| ...` | `att("doc.pdf[...options...]")` — [options table](#options-025--10) |
| custom `@loader` / `@presenter` | one pure function: `@processor(".ext")` (a format) or `@source("proto://")` (an origin) — [DEVELOPMENT.md](../DEVELOPMENT.md) |
| exceptions on bad input | never raises: errors are artifacts with `meta["error"] = {"code", "message"}`; `a.raise_for_errors()` to stop |

Verified against 1.0:

```python
from attachments import att

a = att("report.pdf[pages: 1, images: true]")
print(a)                 # the prompt text — what str(ctx) used to be
a.images                 # [{'name': ..., 'mimetype': 'image/png', 'bytes': ..., 'page': 1}]
a.claude("Summarize.")   # Claude Messages API content (plain dicts, no SDK)
a.openai("Summarize.")   # OpenAI Chat Completions messages
a.chunk(max_chars=4000)  # RAG chunks that keep page boundaries
```

### OpenAI Responses API

```python
content = [
    {"type": "input_text", "text": p["text"]}
    if p["type"] == "text"
    else {"type": "input_image", "image_url": f"data:{p['media_type']};base64,{p['data']}"}
    for p in a.parts()
]
client.responses.create(
    model="gpt-4.1-mini",
    input=[{"role": "user", "content": [*content, {"type": "input_text", "text": "Summarize."}]}],
)
```

`a.parts()` is the provider-neutral form every presenter is built from: each
page's text followed by that page's pictures.

---

## What behaves differently

Your code may run unchanged and still get different results. In order of
how likely you are to notice:

1. **PDFs: no page pictures unless you ask.** 0.25 always added page images
   (tiled 2×2). 1.0 draws only the pages that have no text layer (scans).
   Charts and diagrams are invisible to the model until you add
   `[images: true]`. No tiling: one image per page, longest side 2000 px by
   default, JPEG for scanned pages and PNG for the rest (`max_dim`,
   `image_format`, `quality` to change them).
2. **Word, PowerPoint and Excel: pictures only when you ask.** 0.25 drew a
   picture of every page or slide by default (with LibreOffice, when
   installed). 1.0 does it with `[images: true]` — one picture per page,
   slide (hidden slides included) or sheet, numbered like the text — and
   `[images: auto]` draws them only when LibreOffice is installed. The
   pictures stored inside a file are `[embedded_images: true]`.
3. **Folders: files are read, with an overview first.** For a plain folder
   (`att .` on the command line) 0.25 showed only the tree unless you added
   `[files: true]`. 1.0 starts with an overview (the tree, git branch and
   commit, and what was skipped), then reads the files. `[files: false]`
   gives the old tree view; `[tree: false]` drops the overview. So
   `att("docs/")[0]` is the overview, not the first file.
4. **Folders skip different things.** Skipped by default: secrets (`.env`,
   private keys, credential files), dependencies and generated files
   (`node_modules`, virtual environments, caches, lock files, compiled and
   minified files), hidden files, and whatever `.gitignore` and
   `.attachmentsignore` exclude — with git's full rules, in subfolders and
   parent folders too. Unlike 0.25, folders called `build`, `dist`, `bin`,
   `vendor`, `env`, `out` or `tmp` and `*.log` files are **not** skipped by
   name: real code lives there often enough, so your `.gitignore` decides.
   Wildcard patterns follow the same rules (0.25 applied none). Reading stops
   at 1000 files or 256 MiB (0.25: 1000 files) and the overview says so.
5. **Web pages: text, not a screenshot.** 0.25 opened every page in Chromium,
   took a full-page screenshot and listed every link after the text. 1.0
   downloads the page and writes its main content as Markdown — tables, code
   blocks and formulas kept (0.25 dropped tables and code), menus and footers
   left out (`[main: false]` keeps them), links as plain text
   (`[links: true]` keeps addresses). Screenshots are opt-in
   (`[screenshot: true]`) and come as 1280×800 screens a model can read,
   not one very tall picture. 10× faster without a browser.
6. **Photos come out upright.** A phone photo's orientation tag is applied
   to the pixels, so the model sees it the way you do; `[rotate: 90]` then
   turns it clockwise, as in 0.25.
7. **The text is just the content.** No "File Info", "Document Analysis",
   "Processing Summary" or "Object type" sections; each file is one
   `## <name>` block. Fewer tokens for the same content.
8. **Pictures are not changed.** 0.25 stamped the file name onto images by
   default (`watermark: auto`) — which also told the model the file name.
   1.0 never draws on images. To keep names away from the model, use
   `sources=False` on `to_text`, `parts`, `claude`, `openai` and `chunk`.
9. **Errors are data, not text or exceptions.** 0.25 sometimes raised and
   sometimes wrote "⚠️ Could not process ..." into the prompt. 1.0 never
   raises; a failed file is an artifact with empty text and a typed
   `meta["error"]` (`missing-dependency`, `parse-error`, `unpack-error`, ...).
   Check `a.errors`, or call `a.raise_for_errors()`.
10. **Wrong options are reported.** An unknown or invalid option is listed in
    `meta["warnings"]` with a suggestion ("did you mean 'sheet'?") and the
    file is read without it. The output is quiet: no "[Attachments] Applying
    step ..." lines.
11. **Pages must be named.** `[pages: 1,3,5]`, `[pages: -1]` (last page),
    `[pages: 2-4]` work as in 0.25 — plus `-3-` (last three) and `7-` (to
    the end) — but bare `[3-9]` is no longer page selection: write
    `[pages: 3-9]`. PowerPoint takes `pages` (or `slides`) too.

---

## Options: 0.25 → 1.0

Every option also works as a keyword: `att("doc.pdf", pages="1-4")`.
`att.options(".pdf")` (or `att --options .pdf`) lists what a format accepts;
the full reference is [dsl-options.md](dsl-options.md).

| 0.25 | 1.0 |
|---|---|
| `pages: 1-4`, `pages: 1,3,5`, `pages: -1` | same (PDF, PowerPoint); plus `-3-` and `7-` |
| `images: true/false` | same name and meaning (pictures of pages/slides/sheets); **off by default** |
| `format: plain/markdown/xml/code` | gone — one canonical text per format; shape output with `to_text`, `parts`, `chunk` |
| `select: css` | same (alias `css`); results are Markdown |
| `limit: N` (CSV) | `rows: N` (CSV, TSV, XLSX, XLS); on CSV/TSV the old name `limit` still works |
| `head: true` | `rows: N` |
| `summary: true` | same (CSV, needs pandas) |
| `prompt: ...` | `a.claude("...")` / `a.openai("...")` |
| `truncate: N` | `a.chunk(max_chars=N)` or slice `a.text` |
| `split: paragraphs/sentences/tokens/...` | `a.chunk(max_chars=...)` or `max_tokens=` — page-, sheet- and slide-aware, one strategy |
| `tile: 2x2` | gone (one picture per page) |
| `resize_images: 50%` / `800x600`, `resize` | `max_dim: 800` (longest side in pixels) |
| `rotate: 90` | same (clockwise), applied to the upright photo |
| `crop`, `watermark` | gone |
| `ocr: true/auto` | same (RapidOCR); `ocr_engine: lighton` for a remote engine |
| `lang: fra` (Tesseract) | gone: no language to choose. RapidOCR's models read English, French (accents included) and other Latin-script languages, and Chinese; for other scripts try `ocr_engine: lighton` |
| `files: false` | same: the overview without reading files |
| `files: true` | the default now |
| `ignore: standard/auto/gitignore` | the default rules |
| `ignore: raw,none` | `ignore: none` (only `.git` stays out) |
| `ignore: "*.log,tests"` | `ignore: "*.log, tests/"` — added to the defaults, `.gitignore` syntax; `!name` brings a skipped file back |
| `ignore: minimal` | not supported (warning, default rules apply) |
| `max_files`, `glob`, `recursive` | same; plus `max_size` (default 256 MiB) and `hidden` |
| `dirs_only_with_files`, `mode`, `force` | gone |
| `wait`, `viewport`, `fullpage` (screenshots) | `screenshot: true`, `max_screens` (1280×800 screens; the page settles by itself) |
| — | new: `password` (PDF), `sheet` (XLSX), `delimiter` (CSV), `dpi`, `max_pages`, `image_format`, `quality`, `embedded_images`, `outputs` (notebooks), `model`/`language` (audio), `main`/`links` (web pages), `ref` (GitHub), `tree` |

---

## Formats and sources

| | 0.25 | 1.0 |
|---|---|---|
| PDF | text + page images (pdfplumber) | text (pypdf, pdfminer fallback), page images on request, encrypted PDFs (`password`), OCR for scans |
| Word `.docx` | text + page pictures (LibreOffice) | text, tables; page pictures (`images`), embedded pictures (`embedded_images`) |
| PowerPoint `.pptx` | text + slide pictures (LibreOffice) | text per slide, slide segments, `pages`; slide pictures, embedded pictures |
| Excel `.xlsx` | text (+ sheet pictures with LibreOffice) | one text block per sheet, sheet segments, `sheet`, `rows`; one picture per sheet |
| Old `.doc`, `.ppt`; `.odt`, `.odp`, `.ods` | — | **new** (with LibreOffice) |
| `.xls` | matched, but its text reader (openpyxl) cannot open it | **reads** (xlrd) |
| CSV | text table | Markdown table, delimiter sniffing, optional summary; **TSV new** |
| HTML files, web pages | see above | Markdown, main content, optional screenshots |
| Images (png, jpg, gif, webp, bmp, heic) | yes | yes + **tiff**; OCR on request |
| SVG | text + picture | text; picture with `[images: true]` |
| EPS | text + a note | read as plain text |
| Notebooks `.ipynb` | yes | yes; cell outputs on request |
| Audio (mp3, wav, m4a, flac, ogg, opus) | — | **new**: transcription (`attachments[audio]`) |
| Code and text files | yes | yes, plus anything that looks like text, whatever its extension |
| Files without an extension | — | recognised by content (PDF, images, Office, HTML) |
| Folders, git repositories | yes | yes, with skip rules, limits and overview |
| Wildcards | `*.py`, `**/*.md` | anywhere in the path: `reports/*/summary.md` |
| zip | images inside | **any** zip and tar (`.tar.gz`, ...), nested, with the folder rules |
| URLs | yes | yes; the server's declared type wins over the name; the URL is the source name |
| GitHub | — | **new**: `github://owner/repo[ref: main]` |
| Lists, `Path`, `~`, `file://` | lists | all |
| Specialised PDF/DOCX processors (academic, legal, financial, medical, report) | yes | gone — one processor per format |

---

## New in 1.0

- **Failures never take the batch down** — typed error codes, the install
  command for missing pieces, `raise_for_errors()` when you want an exception.
- **Discoverable options**: `att.options()`, `att --options`, editor
  autocomplete for every option as a keyword, `att.help()`.
- **Pictures next to their page**: `claude()`, `openai()` and `parts()` put
  each page's pictures right after its text.
- **Hide file names** from the model with `sources=False`.
- **RAG chunks** that keep page, sheet and slide boundaries and numbers.
- **Token estimates** that include pictures: `a.tokens`,
  `a.estimate_tokens()`.
- **JSON in and out**: `a.to_wire()` / `Artifacts.from_wire()`.
- **Upright photos**: phone photos are turned the way they are displayed
  before the model sees them.
- **Remote processing**: a self-hosted server (`attachments-server`) or the
  hosted service does what your machine can't (OCR, LibreOffice), with
  automatic fallback when a dependency is missing locally.
- **Agents**: an MCP server (`attachments-mcp`) and a skill for coding agents
  (`att --skill --install`).
- **Safety**: download size caps, zip-bomb guards, private-address (SSRF)
  guard on the server, links leading outside a folder never followed,
  secrets skipped in folders and never attached from prompts.
- **Speed**: no browser for web pages; formats load only when used.

---

## Gone, and what to do instead

| 0.25 | Instead |
|---|---|
| The pipeline grammar (`load \| modify \| present \| refine \| adapt`, `+`), the global pipeline registry | options on `att()`; your own formats and sources as one function each |
| `split` strategies (sentences, paragraphs, tokens, ...) | `chunk(max_chars=...)` / `max_tokens=`, or split `a.text` yourself |
| Tiling, cropping, watermarks, contact sheets, thumbnails | edit `a.images` with Pillow if you need them |
| `format: xml` / `code` / `plain` | one text per format |
| DSPy, Agno and clipboard-image adapters | `a.text` and `a.images` plug into any framework; text to the clipboard: `att file --copy` |
| Highlighting CSS matches in web screenshots | `select:` for the text; `screenshot: true` for the page |
| Tesseract languages (`lang:`) | not needed for Latin-script languages and Chinese; `ocr_engine: lighton` for other scripts |

Something you relied on is missing? Open an issue — in 1.0 most formats and
sources are one function.
