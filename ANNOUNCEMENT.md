# attachments 1.0 — turn anything into LLM-ready artifacts

A year ago I published `attachments`, a Python library for the thing every
LLM developer keeps re-writing: *I have a file (or directory, URL, repo,
spreadsheet) — give me text + images I can put in a prompt, without
installing and learning five parsing libraries.* The 0.25.x series did that
with a composition grammar: `attach("doc.pdf") | load.pdf_to_pdfplumber |
present.markdown | adapt.claude`. People used it, but mostly they used the
one-liner on top of it — and the grammar made everything else harder: harder
to contribute one converter, harder to port to other languages, harder to
explain.

So 1.0 is a rewrite around a different bet: **standardize the output shape,
not the pipeline.** The whole library is now one function:

```python
>>> from attachments import att
>>> att("report.pdf[pages: 1-2, images: true]")
<Artifacts: 1 artifact | 94 chars | ~24 tokens | 2 images>
```

`print()` it and you have the assembled prompt. `.claude("Summarize.")` /
`.openai(...)` give you ready API messages (plain dicts, no SDK imports).
`.chunk(max_chars=4000)` gives segment-aware RAG chunks that never split a
page. Under the sugar, every element is a plain dict with a frozen shape —
`{text, images[], audio[], video[], meta}` — and errors never raise out of
`att()`; they come back as artifacts:

```python
>>> att("missing.pdf")
<Artifacts: 1 artifact | 0 chars | ~0 tokens | 1 error>
  ! missing.pdf: unpack-error — unpack failed: Unsupported or non-existent input: missing.pdf
```

Options live inline in a tiny DSL (`[key: value]` — that's the whole
grammar), each with a kwarg twin, and every processor declares its own
option schema, so discovery is built in:

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

Typos warn instead of failing silently: `Unknown option 'sheets' for .xlsx —
did you mean 'sheet'?`

**Coverage today:** PDF (with automatic OCR for scanned pages via RapidOCR),
XLSX/XLS, DOCX, PPTX, HTML with CSS `select:`, CSV/TSV as real tables,
SVG, images (png/jpg/gif/webp/bmp/tiff/heic, with OCR), Jupyter notebooks,
20+ text/code formats, and audio transcription (mp3/wav/m4a/flac/ogg/opus
via faster-whisper). Sources: local files, directories, globs, zip/tar,
HTTP(S), and `github://owner/repo`. When the extension lies, magic-byte
sniffing routes anyway. The core has **zero required dependencies** —
format support installs as extras (`pip install attachments[pdf]`), or a
self-hosted server with all deps can process for zero-dep clients.

**The part I care about most** is what's underneath: the artifact shape, the
typed `meta` envelope and error codes, and the DSL grammar are frozen in a
one-page spec ([spec/](spec/)) with a JSON Schema and shared parser test
vectors, enforced by a conformance suite in CI. That makes contributing a
format one pure function — `(bytes, options) -> artifact` plus a declared
option schema — and makes ports to other languages a parsing exercise, not
an architecture one. A thin client in any language is a week of work against
the server.

**Migrating from 0.25.x:** the muscle memory carries over —
`Attachments("f.pdf")` → `att("f.pdf")`, `str(ctx)` → `print(a)` / `a.text`,
`ctx.images` → `a.images`, adapters still hang off the result. Pipelines
become DSL options (`[limit:]` is now `[rows:]`). Full side-by-side guide:
[docs/MIGRATION.md](docs/MIGRATION.md). 0.25.x stays on PyPI in maintenance
mode; pin `attachments<1` if you're not ready.

```bash
pip install attachments
```

Repo: https://github.com/MaximeRivest/attachments — the executed demo
notebook is [examples/demo.ipynb](examples/demo.ipynb). Every snippet above
is real output from this release. The long tail (`s3://`, `notion://`,
`.eml`, video, …) is deliberately open — each one is a small pure function
away, and I'd love help.
