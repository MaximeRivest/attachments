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

- **One-function API**: `att(input, **options) -> list[Artifact]` handles
  files, directories, zip/tar archives, HTTP(S) URLs, and `github://` repos.
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
- **Magic-byte routing**: files with missing or lying extensions are routed
  by content sniffing (`%PDF`, PNG/JPEG/GIF magic, zip-container types, ...).
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

### Removed

- **Breaking — the 0.x grammar API is gone.** The `Attachments` class, the
  `load | modify | present | refine | adapt` pipeline grammar, operator
  composition, and the implicit global pipeline registry have no equivalent
  in 1.0. The 0.25.x line remains on PyPI and is in maintenance mode.

### Migration from 0.25.x

The one-liner maps directly: `Attachments("report.pdf")` becomes
`att("report.pdf")`, and where you previously relied on
`str(Attachments(...))` (or `.text`) to build a prompt string, call
`render_text(att("report.pdf"))`. Adapter usage (`.claude()`, `.openai()`)
becomes `to_claude_messages(artifacts, prompt=...)` /
`to_openai_messages(artifacts, prompt=...)`; images are on each artifact's
`images` list; per-format tweaks move from pipeline stages to DSL options or
their kwarg twins (`att("doc.pdf[pages: 1-4]")`). Custom loaders/presenters
become processors or unpack handlers (see
[DEVELOPMENT.md](DEVELOPMENT.md)).

[1.0.0]: https://pypi.org/project/attachments/
