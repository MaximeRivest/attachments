# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0b7] - 2026-10-09

Fixes found by comparing attachments with markitdown and docling on their
own test files and on olmOCR-bench ([evals/compare](evals/compare/README.md)).

### Changed

- **Word documents are read from their XML** (`_docx_text`, standard
  library) instead of through python-docx's object model. Now read:
  content controls (templates and forms; whole tables used to vanish),
  text boxes, the "Strict" format (failed to open before), tracked changes
  (as accepted), equations as plain text. Tables are Markdown tables with
  a header line, a cell's paragraphs on one line (`<br>`), merged cells,
  and a one-cell frame table read as its content. Headings (`#`) and list
  items (`-`, `1.`) are marked. On the 40 Word test files: paragraphs
  found 88.6% -> 100%, table rows 41.7% -> 99.0%. Also no longer slows down
  quadratically on long documents. python-docx is still required, and used
  only for embedded pictures.
- **Small web tables of short values are tables**: Readability's rule
  called every table under ~10 cells without header cells "layout" and
  flattened it into lines. Now a table is layout only when its cells hold
  page structure (a table, form, menu, section) or long text.
- **The `pdf` extra requires pypdf 6.17 or later**: earlier versions run
  the words of some PDFs together ("Toperkone'sselfup"; 10 points lower on
  olmOCR-bench's small-print pages). A project pinning an older pypdf now
  gets a version conflict instead of that text.
- **OCR turns a page only for a confident, clearly better reading that
  reads at least as much text**: an upright handwritten envelope was read
  upside down (its "6" as one confident "9").

## [1.0.0b6] - 2026-10-09

### Changed

- **Photos lose what they say about their owner**: GPS location, dates,
  camera serial, thumbnails (EXIF, XMP, IPTC, comments, trailing data) are
  cut out of JPEG, PNG and WebP files without touching the pixels or the
  colour profile. Applies to images, and to the photos inside Word,
  PowerPoint and web pages. `[metadata: true]` keeps an image's bytes;
  `meta.extra.metadata_removed` lists what went.
- **Token estimates follow Claude's current rule**: 28 x 28 pixel patches
  after Claude's resizing, on the high-resolution tier of Claude 4.7 and
  later (up to 4,784 a picture; a default page picture is about 4,000), so
  budgets hold for every Claude model; `estimate_tokens(tier="standard")`
  for other models (up to 1,568). The old rule (width x height / 750, at
  most ~1,600) under-counted pages on current models by about 2.5 times.
  Checked against Anthropic's reference code (6,014 sizes) and its table.
- **Mistyped options** name the real option with an example ("did you mean
  'pages'? (e.g. [pages: 1-4])", not the alias 'page'), and are reported
  as an `OptionWarning` pointing at your line instead of an unlabelled log
  line.

### Added

- `OptionWarning`, `image_tokens(..., tier=)`, `estimate_tokens(..., tier=)`.

## [1.0.0b5] - 2026-10-09

### Changed

- **Service requests wait 130 s by default** (`timeout`, was 60 s): past
  the hosted server's own 120 s limit, so a long OCR request ends with the
  server's answer instead of a client timeout. A 20-page scan sent to the
  service took 55 s.

### Fixed

- When `ocr_max_pages` stopped OCR (a server's limit), the warning
  suggested `[ocr: true]`, which that limit also bounds, and said "this
  machine", which a service user reads as their own. It now names
  `ocr_max_pages` and suggests `[pages: N-]`.

## [1.0.0b4] - 2026-10-09

### Added

- **`ocr_auto_pages`** (default 50) and **`ocr_max_pages`** (default no
  limit) in `configure()` and as `ATTACHMENTS_OCR_AUTO_PAGES` /
  `ATTACHMENTS_OCR_MAX_PAGES`: pages OCR reads in one document. The second
  also bounds `ocr: true`, for servers whose requests must end in time;
  the warning then says `[pages: N-]` reads the rest.

### Changed

- Hosted service settings (`deploy/`): OCR stops at 10 pages a document
  (its 2 vCPU, one core, read ~4.5 s a page; the client waits 60 s by
  default), container memory 5 GB (each worker peaks ~1.2 GB reading a
  scan).

## [1.0.0b3] - 2026-10-09

Scanned documents: readable text, requests Claude accepts, and no long
silent waits. Every number below is measured on realistic scans with known
text ([evals/scans](evals/scans/README.md)).

### Changed

- **OCR engine: RapidOCR 3 with its PP-OCRv6 models** (the `ocr` extra now
  installs `rapidocr` and `onnxruntime` instead of `rapidocr-onnxruntime`;
  still local and offline, the models ship in the package). Words read
  wrong on scanned pages: from 36-60% to under 0.5%. The old engine lost
  the spaces between words ("Revenuegrewby twelvepercent") and dropped
  accents ("réunion" read "reunion").
- **OCR reads several pages at once** (up to 3, 4 threads each, from the
  machine's cores; `configure(ocr_workers=N)` or
  `ATTACHMENTS_OCR_WORKERS`), with a progress bar on a terminal or in a
  notebook (`configure(progress=False)` or `ATTACHMENTS_PROGRESS=0` to
  hide it). A 20-page scan: 8.3 s a page before, 0.95 s now on a desktop,
  2 s on 2 cores.
- **PDFs are handled page by page.** A page without a text layer gets OCR
  and, with `images: auto`, its picture, also inside an otherwise typed
  PDF (those pages used to be silently empty); blank pages get neither.
- **`image_format: auto` is the default** for PDF and Office page pictures:
  JPEG for a page that pictures (a scan, photos) cover at least half of,
  PNG for the rest. A scanned page is 0.38 MB instead of 2.3 MB, so a
  20-page scan is a 10 MB Claude request instead of 60 MB (the API takes
  32 MB).
- **Automatic OCR stops at 50 pages** per document (`ocr: auto`), with a
  warning that says which pages have no text and how to read them
  (`ocr: true` reads them all). A page count rather than a time limit, so
  the same file always gives the same text.
- Warnings (`meta.warnings`: mistyped options, OCR that stopped early) now
  show in the printed summary, with `!`, and in Jupyter.

### Added

- **`RequestLimitWarning`**: `.claude()` / `to_claude_content()` and
  `.openai()` / `to_openai_messages()` warn when a request breaks a
  published limit (Claude: 32 MB a request, 10 MB a picture, 100 pictures
  for 200k-context models, 8000 px, 2000 px when there are more than 20
  pictures; OpenAI: 512 MB, 1500 pictures; both: JPEG, PNG, GIF, WebP),
  naming the problem and the fix.
- Sideways and upside-down pages are found and read; their pictures are
  delivered upright (`meta.extra.ocr_turned`, page -> degrees).
- Two-column pages are read column by column (tables stay in rows), with
  blank lines between paragraphs.
- `meta.extra.ocr_pages`: the pages OCR read.

### Fixed

- Encrypted PDFs opened with their password: page pictures were missing.

## [1.0.0b2] - 2026-10-09

### Fixed

- **`attachments-mcp` failed to start on a fresh install.** The `mcp` SDK
  2.x renamed its server class (`FastMCP` is now `MCPServer`), and a new
  install gets 2.x; 1.0.0b1 only knew the old name and reported the SDK as
  missing. Both 1.x and 2.x now work, and CI tests both.
- The `mcp` extra asked for `mcp>=1.2`, but the server needs `mcp>=1.17`.
- An installed but unsupported `mcp` is now reported as such, with the
  version to install, instead of "requires the mcp extra".

### Changed

- Releases also start the MCP server from the built package, with the
  newest dependencies, and call its tools over stdio before publishing.

## [1.0.0b1] - 2026-10-09

The first 1.0 version on PyPI, as a beta. 1.0 is a complete rewrite of
attachments: the [1.0.0a1 notes](CHANGELOG.md#100a1---2026-06-09) describe it, and
[docs/MIGRATION.md](docs/MIGRATION.md) is the upgrade guide from 0.25. A
plain `pip install attachments` still installs 0.25 until 1.0.0 is out;
to get this version:

```bash
pip install "attachments>=1.0.0b1"
```

Changes since 1.0.0a1 (June; neither alpha was published) follow. Six additions from the FunctAI review
([docs/review-2026-10-06-functai.md](docs/review-2026-10-06-functai.md)),
useful to every consumer, plus one severe bug fix; web pages rebuilt
(Markdown output, main-content extraction, screenshots); and folders made
safe and readable again (skip rules, limits, overview), with the path
types 0.25 had back.

### Added

- **Pictures of Office pages, slides and sheets** (`images: true`), drawn
  by LibreOffice and the PDF page renderer, with the same `dpi`, `max_dim`,
  `image_format` and `quality` as PDF pages — as 0.25 had. Word, `.doc`
  and `.odt`: one picture per page. PowerPoint, `.ppt` and `.odp`: one per
  slide, hidden slides included so picture N is slide N. Excel, `.xls` and
  `.ods`: one per sheet (whole sheet on one page), in workbook order;
  empty sheets get none. `images: auto` draws them only when LibreOffice is
  installed. Old formats are drawn from the original file, not the
  converted copy. Sheet segments now carry the sheet's position as `page`,
  matching its picture.
- **`embedded_images: true`** (Word, PowerPoint): the pictures stored in the
  file — what `images: true` used to mean.
- **Page lists and pages from the end**: `pages: 1,3,5`, `-1` (last),
  `-3-` (last three), `7-` (to the end), `2--2`; in document order, each
  page once (`attachments._pages`). A selection with no page in the
  document says so instead of returning nothing silently.
- **`pages` for PowerPoint** (alias `slides`): pick slides; their pictures
  and embedded images follow the selection.
- **DSL**: a segment without `:` continues the previous value, so
  `[pages: 1,3,5]` and `[select: h1, p]` need no quotes
  (spec/dsl-grammar.md rule 2a; every previously valid input parses the
  same; new test vectors).
- **Python 3.11** supported (3.11–3.13 in CI); the full suite passes on 3.11
  and 3.13.
- **Folders skip what should not reach a model.** One set of rules for
  folders, patterns, GitHub repos and archive members
  (`_sources/_ignore.py`): secrets (`.env` files, private keys, credential
  files, Terraform state), dependencies and generated files (`node_modules`,
  virtual environments found by their `pyvenv.cfg`, caches found by the
  standard `CACHEDIR.TAG`, lock files, compiled objects, minified bundles),
  hidden files, and `.gitignore` / `.attachmentsignore` with full git
  semantics (negation, anchoring, `**`, nested files, parent folders up to
  the repository root, `.git/info/exclude`) — checked against
  `git check-ignore` in the tests. Ambiguous names (`build`, `bin`,
  `vendor`, `env`) are not guessed at; `.gitignore` decides.
- **Folder options** (`att.options("file://")`, also on `github://`):
  `ignore` (more patterns; `!name` brings one back; `none` skips nothing
  but `.git`), `hidden`, `glob` (alias `include`: only matching files),
  `recursive`, `max_files` (default 1000), `max_size` (default 256 MiB,
  `50MB`-style values; `0` = no limit), `files: false` (the overview only,
  nothing read) and `tree`. A file too big for what is left of `max_size`
  is skipped and reading goes on.
- **Folder overview**: folders and repositories start with a
  `kind: "directory"` artifact — the file tree, git branch, commit and
  origin (credentials removed; read from `.git`, never by running git),
  and what was skipped, by reason, with how to get it back. Patterns and
  archives get it only when a limit was hit or nothing was read
  (`tree: true/false` overrides). `sources=False` leaves overviews out, as
  they are made of file names.
- **`att()` takes lists** (any iterable, nested, read in order; options
  apply to each), **`pathlib.Path`**, **`~/...`** and **`file://` URIs**.
  An input that is not a path becomes an `unpack-error` artifact.
- **Wildcards anywhere in a path**: `reports/*/summary.md`, and invalid
  sets like `[x-f]` are literal. Patterns follow the skip rules too, so
  `**/*.js` no longer pulls in `node_modules`; when nothing matches because
  everything was skipped, the error says so and how to include them.
- **`att.from_prompt(prompt, root=..., urls=False, **options)`**, the
  successor of 0.25's `auto_attach`: attaches the files a prompt mentions
  (backticks, quotes, bare names with an extension, DSL options included),
  in order, once each. Mentions are untrusted: confined to the root folders
  (no `..`, absolute paths or links out), secrets never attached, URLs only
  with `urls=True`.
- **Old Office and OpenDocument files** — `.doc`, `.ppt`, `.odt`, `.odp`,
  `.ods` — converted by LibreOffice, then read by the docx/pptx/xlsx
  processors with their options (images, slide segments). LibreOffice is a
  program, not a pip package: without it the error says how to install it
  (`ATTACHMENTS_LIBREOFFICE` points at a specific `soffice`). Each
  conversion gets its own profile and is killed after
  `ATTACHMENTS_LIBREOFFICE_TIMEOUT` seconds (default 120).
- **Server image draws Office pages**: fonts with the widths of Arial,
  Times, Courier, Calibri and Cambria (Liberation, Carlito, Caladea) so
  pages break where Office breaks them, and Noto for other scripts
  (Arabic, Hebrew, Indic, Chinese, Japanese, Korean...); +150 MB, 1.87 GB.
  The build also draws a page (`warmup.py --strict`).
- **Server image converts old Office files**: `deploy/Dockerfile` installs
  LibreOffice (writer/impress/calc, no GUI; +0.42 GB, 1.72 GB total) and
  `tini` as PID 1, caps conversions at 60 s (under gunicorn's 120 s), and
  the build fails unless OCR and a real `.doc` conversion work
  (`warmup.py --strict`). Clients without LibreOffice get these files
  converted by the service. Base images are fully qualified so Podman
  builds it too; the wheel is found by pattern instead of a stale default
  version. First verified build of the deploy kit.
- `attachments._sources.resolve()` returns files plus a `TreeReport` per
  tree; `unpack()` keeps its exact shape and gained `options=`.

- **Public wire form**: `Artifacts.to_wire()` / `Artifacts.from_wire(data)`
  and the per-artifact `artifact_to_wire()` / `artifact_from_wire()`
  (images as base64 `bytes_b64`, valid against `spec/artifact.schema.json`).
  `to_wire` returns new dicts and never modifies its input; `from_wire`
  raises `ValueError` on invalid base64 or wrongly typed fields. The server,
  the service client and the CLI now share this one implementation.
- **`to_parts()` / `Artifacts.parts()`**: provider-neutral content parts
  (`{"type": "text", "text"}`, `{"type": "image", "media_type", "data"}`),
  with each page's text followed by that page's images (`interleave=True`,
  the default). `claude()` / `openai()` and `to_claude_*` /
  `to_openai_messages` are now built from it and take the same options.
- **`Artifacts.raise_for_errors()`** and **`AttachmentsError`** (`.errors`,
  `.artifacts`; picklable). Opt-in: `att()` itself still never raises.
- **`sources=` everywhere** (`to_text`, `parts`, `claude`, `openai`,
  `chunk`, and the plain functions): `False` hides file names.
- **Page image size control for PDFs**: `max_dim`, `image_format`
  (`png`/`jpeg`) and `quality` (1–95, default 85). Pages are drawn at the
  final size directly. Pictures gain `image_format` and `quality` with the
  same meaning; `max_dim: 0` means "no limit" for both.
- **Image tokens in the estimate**: `estimate_tokens()` /
  `Artifacts.estimate_tokens()` → `{"text", "images", "total"}`, and
  `image_tokens(w, h)`. Image sizes are read from PNG/JPEG/GIF/WebP/BMP
  headers with the standard library only.
- **A skill for coding agents**, shipped in the package
  (`attachments/skill/`: `SKILL.md` plus an `options.md` generated from the
  option schemas), and **`att --skill [--install [DIR ...]]`** to see and
  install it for Claude Code, Pi and Codex. Installs replace only this
  skill's own copies, leave links alone, and swap the new copy in
  atomically. Every Python example in `SKILL.md` runs in the test suite;
  `evals/skill/` measures it with fresh agents.
- **`Segment.page`** (optional, 1-based) in the IR: pdf page and pptx slide
  segments carry the same number as `ImageItem.page`. Additive; schema stays
  version 1.
- **Web pages read as Markdown.** HTML (from a URL or a file) becomes
  headings, lists, pipe tables, fenced code blocks with their language and
  TeX maths, with sentences kept whole across links and emphasis. Data
  tables become Markdown tables (`rowspan` values repeat, spacer columns
  drop); layout tables — whole old-web pages are built from them — read as
  paragraphs (Mozilla Readability's data-table test).
- **`main`** (html, default `true`): only the page's main content —
  navigation, site header/footer, sidebars, dialogs, cookie/share widgets and
  MediaWiki edit links are skipped, following how browsers expose page
  landmarks (an article's own header and asides stay). A single `<main>` is
  used as the scope. Nothing is dropped by text statistics, so content
  tables and link lists stay; if skipping would leave almost nothing, the
  whole page is used (`extra.main_fallback`). `main: false` keeps everything.
- **`links`** (html, default `false`): `[text](url)` links and
  `![alt](url)` images, with relative addresses resolved.
- **`url`** (html): the page's address. Filled in automatically for web
  pages with the final address after redirects (core passes it to any
  processor that declares a `url` option, locally and to the service), so
  relative links resolve correctly.
- **`screenshot`** (html, needs the new `browser` extra and
  `playwright install chromium`, or `ATTACHMENTS_CHROMIUM` set to a
  Chromium/Chrome executable): adds pictures of the page rendered in
  headless Chromium, as 1280×800 screens from the top (`max_screens`,
  default 5; `0` = whole page), with the shared `max_dim`, `image_format`
  and `quality` options. A web page is loaded from its address, a local
  file from its bytes. Runs on a worker thread, so it works in Jupyter.
  When private addresses are blocked (`ATT_BLOCK_PRIVATE_URLS`, and always
  on the self-hosted server unless `ATTACHMENTS_ALLOW_PRIVATE_URLS`), every
  request the page makes must pass the SSRF guard.
- HTML whose text is almost empty but has scripts gets a `meta.note` saying
  it is probably built by JavaScript and suggesting `screenshot: true`.
- `attachments._sources.SourceFile`: what HTTP downloads return from
  `unpack()` — still exactly a `(name, bytes)` tuple, plus `.url` and
  `.warnings`.

### Changed

- **PDF page images are capped at 2000 px on the longest side by default**
  (was: no cap; a 200 dpi slide-sized page was 2667 px). Claude shrinks
  anything over 1568 px and OpenAI anything over 2048 px, and Anthropic
  rejects images over 2000 × 2000 in requests with more than 20 images.
  `max_dim` wins over `dpi`; `max_dim: 0` restores the old output.
- `.tokens` and the repr now include images:
  `~3.2k tokens (images ~3.2k)`. An image whose size cannot be read counts
  as the maximum (~1,600).
- `claude()` / `openai()` order content page by page (was: all text, then
  all images). `interleave=False` gives the old order.
- `render_text(include_sources=...)` is renamed `render_text(sources=...)`.
  With `sources=False`, image-only notes read `[image]` (was
  `[image: <name>]`, which leaked the name).
- An empty `prompt=""` no longer adds an empty text block (APIs reject
  empty text blocks).
- CLI `--json` emits the wire form (`bytes_b64`); it used to put base64 under
  `bytes`, which matched no schema.
- OCR (pdf and image) reads a full-size, lossless image even when the
  delivered images are shrunk or JPEG.
- JPEG output of transparent images is flattened onto white (was: black).
- **`images: true` on Word and PowerPoint draws pages and slides** (was:
  the embedded pictures, now `embedded_images: true`).
- **`rotate` turns clockwise** (was counterclockwise), like 0.25, CSS and
  ImageMagick; negative values turn counterclockwise.
- **Photos are delivered upright**: an EXIF orientation tag is applied to
  the pixels (`extra.exif_orientation`). Re-encoded photos used to drop the
  tag and come out sideways; `rotate` is now relative to what you see.
- **Folders read differently**: they start with the overview artifact
  (so `att("docs/")[0]` is no longer the first file — `[tree: false]`
  restores that), and secrets, dependencies, hidden and `.gitignore`'d
  files are skipped (`.gitignore` used to be honoured only at the top
  level, without `!`). Reading stops at 1000 files / 256 MiB.
  `unpack()` applies the same rules.
- Pattern results come in folder order (a folder's files, then its
  subfolders), like folders; they used to be sorted as full paths.
- GitHub clones are deleted once read (they used to pile up in the temp
  folder, one per call).
- **HTML text is Markdown** (was: plain text with a line break at every
  inline tag). `select:` results are Markdown too (`select: h1` gives
  `# Title`). The page title is prefixed as `# Title` only when the page has
  no `<h1>`.
- **A downloaded file's `meta.source` is its URL** (final, after
  redirects), so prompts read `## https://example.com/` instead of
  `## download`. Its name (`extra.filename`) follows the server's
  Content-Type: a bare `/` is `index.html`, and a specific type that
  contradicts the extension appends the right one (`README.md` served as a
  web page becomes `README.md.html`, `/pdf/1706.03762` served as PDF
  becomes `1706.03762.pdf`). Generic types (`text/plain`,
  `application/octet-stream`, `application/json`) never rename.

### Fixed

- A PDF too broken to count its pages took about 3 minutes and gigabytes of
  memory: the pdfminer fallback built a set of 10^9 page numbers. It now
  fails in well under a second. (Also cut the full test suite from ~7 min
  to ~1.5 min.)
- Importing PyMuPDF as `fitz` printed a deprecation warning into users'
  output with PyMuPDF 1.28; it is now imported as `pymupdf`.
- `Artifacts`' docstring claimed `json.dumps` works on it; it fails as soon
  as there is an image. Docs now point to `to_wire()`.
- A GitHub file page (`https://github.com/o/r/blob/main/README.md`) put
  ~250,000 characters of raw page HTML into the prompt: the `.md` name sent
  it to the text processor. It is now read as a web page, with a warning
  that names the `raw.githubusercontent.com` address of the file itself.
- Web pages lost their sentence flow (every link, bold word and highlighted
  code token on its own line), and tables and code had no structure.
- `att(["a.pdf", "b.csv"])` and `att(Path(...))` raised `AttributeError`
  instead of returning artifacts.
- CLI: several option flags (`att doc.pdf --pages 1 --images true`) made
  several `[...]` groups and only the last was read; flags with dashes
  (`--max-files`) never matched an option. Flags now merge into one set of
  options, typed like DSL values.
- A symbolic link inside a folder (or a cloned repository) could make
  attachments read any file on the machine; links leading outside the
  folder are no longer followed. Named pipes no longer hang a folder walk,
  and an unreadable subfolder no longer fails the whole folder.

## [1.0.0a1] - 2026-06-09

Not published to PyPI.


A complete rewrite of `attachments`, succeeding the 0.25.x series. The
project's center of gravity moved from a composition grammar to a small,
language-neutral protocol: one function in, one frozen output shape out.
See [VISION.md](VISION.md) for the reasoning.

### Added

- **One-function API**: `att(input, **options) -> Artifacts` handles
  files, directories, zip/tar archives, HTTP(S) URLs, and `github://` repos.
  Directory walks are deterministic (sorted), so artifact order — and
  therefore `.text`, `.chunk()`, and the repr — is the same on every
  filesystem and machine.
- **`Artifacts` container**: `att()` returns a `list` subclass whose elements
  stay plain Artifact dicts (the IR is untouched — pure sugar around it).
  The repr is a one-line summary plus one `!` line per error (capped at 10,
  the rest collapse into `+N more errors (see .errors)`) and never dumps
  text/bytes; `str()`/`.text` is the assembled prompt (`render_text` — v1's
  `print(ctx)` muscle memory); `.images`/`.errors` flatten the common parts;
  `.claude(prompt=None)`/`.openai(prompt=None)`/`.chunk()` are last-mile
  shortcuts (`prompt=` is now optional in `to_claude_messages` /
  `to_openai_messages` too); slices and concatenation stay `Artifacts`; and
  `_repr_markdown_` gives Jupyter a summary, error admonitions, a text
  preview, and capped inline image thumbnails.
- **Generated typing stub (kwargs autocomplete)**: `__init__.pyi` is
  generated from the declared option schemas by
  `scripts/gen_dsl_assets.py` — one typed named parameter per DSL option
  AND alias across all schemas on `att()` (e.g. `pages: int | str |
  tuple[int, int]`), plus typed `att.options`/`att.help` — so the kwarg
  twin autocompletes in any editor with no plugin. Sync-tested in CI like
  the other generated assets.
- **Pretty `att.options()` + `att.help()`**: `options()` returns the same
  JSON-serializable data wrapped in repr-friendly subclasses that print
  aligned plain-text option tables in the REPL, and `att.help()` prints a
  one-screen overview (formats grouped from the live registry, sources,
  copy-pasteable examples, pointers) — no network, instant.
- **Frozen Artifact IR**: every processor produces, and every consumer
  accepts, `{text, images[], audio[], video[], meta}` with a **typed meta
  envelope** (`source`, `kind`, `via`, `error{code,message}`, `note`,
  `warnings`, `segments`, `extra`) and typed error codes
  (`missing-dependency`, `password-required`, `parse-error`, `unpack-error`,
  `service-error`, `invalid-option`, `processing-error`). Errors never raise
  out of `att()`. Contract: [spec/IR-CONTRACT.md](spec/IR-CONTRACT.md), JSON
  Schema: [spec/artifact.schema.json](spec/artifact.schema.json).
- **Two open registries**: processors (*WHAT is it?* — `@processor(".myf")` /
  `register_processor`) and unpack handlers (*WHERE does it come from?* —
  `@source("myproto://")` / `register_unpack_handler`). Source × format
  multiply; adding either never means editing core.
- **DSL with per-processor option schemas**: inline options
  (`att("report.pdf[pages: 1-4, images: true]")`) resolve against schemas
  each processor declares (`Option(name, type, aliases, param, default,
  help, example)`). Unknown keys never fail silently — they warn with
  "did you mean ...?" in `meta.warnings`. Every DSL option has a
  keyword-argument twin; explicit kwargs win. Grammar + shared parser test
  vectors: [spec/dsl-grammar.md](spec/dsl-grammar.md).
- **Runtime option discovery**: `att.options(".pdf")` /
  `attachments.options()` / `dsl_schema()`, plus `att --options` on the CLI,
  `GET /options` on the server, and the generated cheatsheet in
  [docs/dsl-options.md](docs/dsl-options.md).
- **Processors**: text (20+ extensions, zero deps), PDF (pypdf/pymupdf —
  pages, password, image rendering, dpi), XLSX (openpyxl/pandas), DOCX
  (python-docx), PPTX (python-pptx), HTML (beautifulsoup4/lxml), and images
  png/jpg/gif/webp/bmp/tiff (Pillow). Multi-part formats populate
  `meta.segments` (pages/sheets/slides with offsets into `text`).
- **CSV/TSV processor** (stdlib, zero deps): delimiter sniffing, markdown
  pipe tables capped at `rows` (default 200), and an optional pandas
  `summary: true` section (`attachments[csv-pandas]`).
- **Legacy Excel (.xls)** via xlrd (`attachments[xls]`) — identical
  all-sheets layout, `sheet`/`rows` options, and `meta.segments` as XLSX.
- **HEIC/HEIF images** via pillow-heif (`attachments[heic]`), with
  extension- and ftyp-brand-based detection; plus a `rotate:` option for
  all raster images (counterclockwise degrees, applied before `max_dim`).
- **SVG processor** (stdlib text extraction for .svg/.svgz, including
  gzipped sources) with optional cairosvg rasterization
  (`attachments[svg]`, `images: true`).
- **HTML `select:` option** (alias `css`): extract only the elements
  matching a CSS selector, preserving the page title.
- **Glob patterns as input**: `att("src/**/*.py")` expands recursive
  globs deterministically (sorted, regular files only), with archive
  expansion and a clear error naming the pattern on zero matches.
- **Magic-byte routing**: files with missing or lying extensions are routed
  by content sniffing (`%PDF`, PNG/JPEG/GIF magic, zip-container types, ...).
- **OCR for scanned PDFs and images** via RapidOCR (`attachments[ocr]`,
  kept out of `all-local` because onnxruntime is large): a shared `ocr:`
  option (`true`/`false`/`auto`) on the PDF and image processors —
  `auto` (PDF default) kicks in only when a page has no text layer; the
  engine is cached, and its C++ stderr chatter is silenced at the fd level.
- **Jupyter notebook processor** (`.ipynb`, stdlib-only): markdown cells
  verbatim, code cells fenced with the notebook language, optional
  `outputs: true` to include execution outputs (text fenced and truncated
  at ~2000 chars each; `image/png` outputs become image items).
- **Audio transcription processor** (mp3/wav/m4a/flac/ogg/opus) via
  faster-whisper (`attachments[audio]`, kept out of `all-local` because
  ctranslate2 is large): `model:` (tiny..large-v3, default base, cached
  per name, CPU/int8) and `language:` (autodetect by default) options;
  bytes transcribed in-memory, no temp files.
- **Token approximation layer**: `Artifacts.tokens` (ceil of chars/4 — a
  fast approximation, not a tokenizer), a `~N tokens` segment in the
  `Artifacts` repr/Jupyter summary, and `chunk(..., max_tokens=N)` as the
  token-budget twin of `max_chars` (`max_tokens=N` == `max_chars=N*4`).
- **Last mile** (`attachments.render`): `render_text` (prompt string with
  `## <source>` headers), `to_claude_content` / `to_claude_messages` (Claude
  Messages API blocks, plain dicts, no SDK import), `to_openai_messages`
  (Chat Completions parts with data-URL images), and `chunk`
  (deterministic, segment-aware chunking for RAG).
- **Hybrid local/service processing**: `configure(api_key=..., service_url=...)`
  plus `prefer="local" | "service" | "local-only" | "service-only"`. Fallback
  is driven by the typed `missing-dependency` error code, never by message
  string-matching.
- **Self-hosted server**: `attachments-server` (stdlib HTTP) and a WSGI
  `create_app()` for gunicorn, with Bearer-token auth
  (`ATTACHMENTS_SERVER_KEY`), upload limits (`ATTACHMENTS_MAX_UPLOAD`), and
  endpoints `POST /process`, `POST /unpack`, `GET /health`, `GET /formats`,
  `GET /options`.
- **CLI**: `att` / `attachments` — prints extracted text, accepts DSL
  inline or as `--key value` flags, `--json`, `--copy --prompt` (clipboard
  support via the `clipboard` extra), `--prefer`, `--options`. Exits
  nonzero when every input failed (each artifact carries `meta.error`);
  partial success still exits 0.
- **MCP server**: `attachments-mcp` (`mcp` extra) exposes two tools to any
  MCP-capable agent — `att(source, options)` (universal ingestion: text
  first, then page/slide images capped at 6 / 1.5 MB each, errors and
  teaching notes returned as readable text under `--- notes ---`, never
  exceptions) and `att_options(extension)` (per-format option tables).
  Stdio transport; `--help` prints Claude Code / Claude Desktop config
  snippets; `ATTACHMENTS_SERVICE_URL` enables hosted-tier passthrough.
- **Typed plugin contract**: `attachments.Processor` protocol —
  `(data: bytes, *, filename=None, **options) -> Artifact` — is the
  type of the processor registry and `register_processor`/`processor`,
  matching the frozen IR contract.
- **spec/ + conformance suite**: the IR contract, artifact JSON Schema, DSL
  grammar, and shared DSL test vectors, validated in CI against every
  registered processor (new processors are picked up automatically) and
  against live server responses.
- **Zero required dependencies**: the core package installs nothing;
  everything optional lives in extras (`pdf`, `xlsx`, `docx`, `pptx`,
  `html`, `image`, `service`, `clipboard`, `office`, `all-local`,
  `server`).

### Security

- **Upload caps enforced everywhere**: both server code paths (stdlib
  handler and WSGI `create_app()`) reject request bodies larger than
  `ATTACHMENTS_MAX_UPLOAD` with HTTP 413 *before* reading them — on
  `/process` and `/unpack` alike.
- **Decompression-bomb guards**: archive expansion is capped by total
  uncompressed size (`ATT_MAX_EXPANSION_BYTES`, default 1 GiB) and nesting
  depth (`ATT_MAX_ARCHIVE_DEPTH`, default 8); zip/tar bombs raise a typed
  `unpack-error` instead of exhausting memory.
- **SSRF guard on the server**: `/unpack` refuses URLs (and redirect
  targets) that resolve to loopback, link-local (cloud metadata), or
  private-range addresses; opt out with `ATTACHMENTS_ALLOW_PRIVATE_URLS=1`.
  Library/CLI use is unaffected by default (opt in with
  `ATT_BLOCK_PRIVATE_URLS=1` or `unpack(..., block_private_urls=True)`).
- **No internal-error disclosure**: unexpected server failures return a
  generic `{"error": "Internal error"}` 500 body; details stay in the
  server log. Client-input problems remain specific 4xx messages.
- **Validated environment config**: `ATTACHMENTS_TIMEOUT` is coerced to a
  number and `ATTACHMENTS_PREFER` is validated like `configure()` input —
  a typo'd mode now raises instead of silently behaving like `local`.

### Internal

- **Source-handling layout**: the private `_unpack.py` module was split into
  the `src/attachments/_sources/` package — registry & `unpack()` dispatch in
  `__init__.py`; one module per source (`local`, `archives`, `http`,
  `github`); shared security guards (expansion budget, member sanitization,
  SSRF) in `_guards.py` — mirroring `_processors/`. No user-facing change:
  the public API (`unpack`, `register_unpack_handler`, `source`,
  `extra_unpack_handlers`), dispatch order, env vars, and behavior are
  identical.

### Removed

- **Breaking — the 0.x grammar API is gone.** The `Attachments` class, the
  `load | modify | present | refine | adapt` pipeline grammar, operator
  composition, and the implicit global pipeline registry have no equivalent
  in 1.0. The 0.25.x line remains on PyPI and is in maintenance mode.

### Migration from 0.25.x

Full side-by-side guide: [docs/MIGRATION.md](docs/MIGRATION.md). In short:
the one-liner maps directly: `Attachments("report.pdf")` becomes
`att("report.pdf")`, and the muscle memory carries over: `str(att(...))`
(or `.text`) is still the assembled prompt string, and adapter usage
(`.claude(prompt)`, `.openai(prompt)`) still hangs off the result — they
are sugar for `render_text` / `to_claude_messages` / `to_openai_messages`,
which also accept any plain artifact list. `.images` flattens each
artifact's `images` list; per-format tweaks move from pipeline stages to
DSL options or their kwarg twins (`att("doc.pdf[pages: 1-4]")`). Custom
loaders/presenters become processors or unpack handlers (see
[DEVELOPMENT.md](DEVELOPMENT.md)).

[1.0.0b7]: https://pypi.org/project/attachments/1.0.0b7/
[1.0.0b6]: https://pypi.org/project/attachments/1.0.0b6/
[1.0.0b5]: https://pypi.org/project/attachments/1.0.0b5/
[1.0.0b4]: https://pypi.org/project/attachments/1.0.0b4/
[1.0.0b3]: https://pypi.org/project/attachments/1.0.0b3/
[1.0.0b2]: https://pypi.org/project/attachments/1.0.0b2/
[1.0.0b1]: https://pypi.org/project/attachments/1.0.0b1/
