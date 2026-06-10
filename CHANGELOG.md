# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-06-09

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

[1.0.0]: https://pypi.org/project/attachments/
