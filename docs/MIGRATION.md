# Migrating from attachments 0.25.x to 1.0

1.0 is a complete rewrite. The composition grammar
(`load | modify | present | refine | adapt`) is gone; in its place is one
function with one frozen output shape. The good news: the everyday muscle
memory maps one-to-one, and most migrations are a rename.

The 0.25.x line stays on PyPI in maintenance mode (bug fixes only). Pin
`attachments<1` if you need the old API while you migrate.

## The one-liner

| 0.25.x | 1.0 |
|---|---|
| `from attachments import Attachments` | `from attachments import att` |
| `ctx = Attachments("report.pdf")` | `a = att("report.pdf")` |
| `str(ctx)` / `f"{ctx}"` | `str(a)` / `print(a)` / `a.text` |
| `ctx.images` (base64 strings) | `a.images` (ImageItem dicts: `{name, mimetype, bytes, page}`) |
| `ctx.claude("prompt")` | `a.claude("prompt")` |
| `ctx.openai("prompt")` / `.openai_chat(...)` | `a.openai("prompt")` |
| `ctx[0]` (Attachment object) | `a[0]` (plain artifact dict — see [spec/IR-CONTRACT.md](../spec/IR-CONTRACT.md)) |
| `Attachments("a.pdf", "b.csv")` / `Attachments([...])` | `att(["a.pdf", "b.csv"])` (or `att("a.pdf") + att("b.csv")`) |
| `auto_attach(prompt, root_dir=...)` | `att.from_prompt(prompt, root=...)`, then `.claude(prompt)` — URLs need `urls=True` |
| exceptions on bad input | never raises — errors are artifacts with typed `meta["error"]` |

All verified against 1.0:

```python
from attachments import att

a = att("report.pdf[pages: 1, images: true]")
print(a)            # the assembled prompt — exactly what str(ctx) used to be
a.text              # same string
a.images            # [{'name': ..., 'mimetype': 'image/png', 'bytes': ..., 'page': 1}]
a.claude("Summarize.")   # Claude Messages API dicts (plain dicts, no SDK)
a.openai("Summarize.")   # OpenAI Chat Completions messages
a.chunk(max_chars=4000)  # segment-aware RAG chunks
```

If you previously sent `ctx.images` (base64 strings) to an API yourself,
you usually don't need to anymore — `a.claude()` / `a.openai()` build the
image blocks for you. If you do need raw base64:
`base64.b64encode(item["bytes"]).decode()` per `ImageItem`.

## Pipelines → DSL options (or kwargs)

`load | modify | present | refine | adapt` pipelines have no equivalent.
Each common pipeline collapses into DSL options on `att()` (every option
also has a kwarg twin — `att("doc.pdf", pages="1-4")`):

| Common 0.25.x pipeline | 1.0 |
|---|---|
| `attach("doc.pdf") \| load.pdf_to_pdfplumber \| present.text` | `att("doc.pdf")` — backend is picked for you |
| `... \| modify.pages` via `"doc.pdf[3-9]"` | `att("doc.pdf[pages: 3-9]")` |
| `... \| present.images` (page renders) | `att("doc.pdf[images: true, dpi: 300]")` |
| `... \| modify.limit` via `[limit: 10]` | `att("data.csv[rows: 10]")` — **`limit:` is renamed `rows:`** |
| `... \| modify.select` via `[select: h1]` | `att("page.html[select: h1]")` — same name, CSS selector |
| `[format: plain]` / `present.markdown` etc. | gone — processors emit one canonical text rendering; use `attachments.render` (`render_text`, `chunk`, `to_claude_messages`, `to_openai_messages`) for output shaping |
| `refine.truncate` | `chunk(a, max_chars=N)` or slice `a.text` |
| `adapt.claude(ctx, "prompt")` | `a.claude("prompt")` or `to_claude_messages(artifacts, prompt=...)` |
| custom `@loader` / `@presenter` | one pure function: `@processor(".ext")` (format) or `@source("proto://")` (origin) — see [DEVELOPMENT.md](../DEVELOPMENT.md) |

## DSL changes

The bracket syntax survives, now with per-processor declared schemas:

- `[pages: 1-4]` — pages must be named now (bare `[3-9]` is no longer
  page selection).
- `[limit: N]` → `[rows: N]` (CSV/TSV, XLSX, XLS).
- `[select: css]` — unchanged for HTML (alias `css:`).
- Web pages: 0.25 listed every link in a "Links" section after the text
  and took a screenshot by default. 1.0 writes the main content as Markdown
  (tables and code blocks included, which 0.25 dropped), links as plain
  text unless `[links: true]`, and screenshots only with
  `[screenshot: true]`. `[main: false]` keeps navigation and footers.
- `[format: ...]` — gone; there is one canonical text per format.
- Unknown keys never fail silently — they warn in `meta["warnings"]`:
  `"Unknown option 'sheets' for .xlsx — did you mean 'sheet'?"`.
- Discover everything at runtime: `att.options(".pdf")`, `att.options()`,
  `att --options`, or the generated cheatsheet in
  [docs/dsl-options.md](dsl-options.md).

## Folders

Folder options keep their names; what they do is more careful:

| 0.25 | 1.0 |
|---|---|
| `[files: false]` — structure only | same: the overview (tree, git, what was skipped) without reading files |
| `[files: true]` | the default: an overview, then the files (`[tree: false]` for files only) |
| `[ignore: standard]` / `auto` / `gitignore` | the default rules: secrets, dependencies, hidden files, `.gitignore` and `.attachmentsignore` (full git rules) |
| `[ignore: raw,none]` | `[ignore: none]` (only `.git` stays out) |
| `[ignore: "*.log,tests"]` | `[ignore: "*.log, tests/"]` — added to the defaults, `.gitignore` syntax, `!name` brings a skipped file back |
| `[ignore: minimal]` | not supported (warns, default rules apply) |
| `[max_files: N]` | same; default 1000, `0` = no limit; plus `max_size` (default 256 MiB) |
| `[glob: "*.py"]` | same, comma-separated, `.gitignore` syntax (alias `include`) |
| `[recursive: false]` | same |

Differences to know:

- 0.25 skipped `build/`, `dist/`, `bin/`, `vendor/`, `env/`, `out/`, `tmp/` and
  `*.log` by name. 1.0 does not guess from names (real code lives there
  often enough): a project's `.gitignore` decides. Virtual environments and
  caches are recognised by their marker files instead.
- Wildcard patterns follow the same skip rules (0.25 applied none).
- `.doc` and `.ppt` work with LibreOffice installed.

## What has no replacement

- Operator composition (`|`, `+` on pipeline stages) and the global
  pipeline registry: intentionally removed (see [VISION.md](../VISION.md)).
- Highlighting matched elements in URL screenshots (`[select: ...]` drew
  boxes on the screenshot): not ported. Page screenshots themselves are
  back as an opt-in: `att("https://x.org[screenshot: true]")` (needs
  `attachments[browser]`). Unlike 0.25 they are screen-sized 1280×800
  images rather than one very tall picture, so a vision model can read them.
- `.dspy()` adapter: not ported — `a.text` and `a.images` plug into any
  framework.

If a 0.25.x feature you rely on is missing, open an issue — the 1.0
processor contract makes most of them an afternoon of work.
