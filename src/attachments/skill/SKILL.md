---
name: attachments
description: Use when Python code must turn files, folders, URLs, zip archives or GitHub repos (PDF, Word, Excel, PowerPoint, CSV, HTML, notebooks, images, audio) into text and images for a language model, with the `attachments` library (`from attachments import att`). Covers installing 1.0 (a plain `pip install attachments` gets the old 0.25 API), page, sheet and image options, Claude, OpenAI or provider-neutral messages with each page's picture next to its text, hiding file names from the model, stopping on unreadable files, image size and token budgets, RAG chunks with page numbers, and saving results as JSON.
---

# Attachments 1.0: any file to text and images for a model

`att("report.pdf")` reads almost anything and returns `Artifacts`: a list of
plain dicts, one per file, each `{text, images, audio, video, meta}`. Most of
the library is that one call; this page covers what goes wrong around it.
All option names: `options.md` next to this file (generated from the code).

## 1. Make sure it is 1.0 (check before writing code)

```bash
python -c "import attachments as a; print(a.__version__, hasattr(a, 'att'))"
```

- `False`, or no module: install 1.0. **`pip install attachments` and
  `uv add attachments` install 0.25**, the old API (1.0 is a pre-release):

  ```bash
  uv add "attachments[pdf,image]>=1.0.0b1"
  pip install "attachments[pdf,image]>=1.0.0b1"
  ```

  The `>=1.0.0b1` is what selects 1.0; `--pre` is not needed (and with pip
  it would also pull pre-releases of every other package).

  A local checkout: `uv add --editable /path/to/attachments`.
- Never write 0.25 code, which models remember: `Attachments("f.pdf")`,
  `attach(...) | load.x | present.y`, `ctx.images` as base64 strings,
  `[format: ...]`, `adapt.claude(...)`.
- Extras: `pdf`, `image`, `docx`, `xlsx`, `pptx`, `html`, `all-local`; `ocr` and
  `audio` are large; `browser` (web page screenshots) also needs
  `playwright install chromium`. The core has no dependencies and reads text, code, CSV
  and JSON. A missing extra raises nothing: that file comes back with error
  code `missing-dependency` and the exact `pip install` command.

## 2. The one call

```python
from attachments import att

a = att("report.pdf[pages: 2-4, images: true]")  # options in [...]
a = att("report.pdf", pages="2-4", images=True)  # the same, as keywords
a = att("docs/")                                 # a folder (recursive); also .zip, .tar
a = att("scans/*.pdf")                           # a wildcard (anywhere: "*/a.md")
a = att("https://example.com/paper.pdf")         # a URL
a = att("github://owner/repo[ref: main]")        # a repository
a = att(["report.pdf", "chart.png"])             # several inputs (str or Path)
```

`print(a)` or `a.text` is the prompt text, each file under `## <name>`;
`a[0]` is a plain dict; `a.images` lists `{name, mimetype, bytes, page}`.

**Folders** start with an overview artifact (`meta["kind"] == "directory"`:
file tree, git branch, what was skipped), so `att("docs/")[0]` is not a
file; `[tree: false]` drops it. Secrets (`.env`, keys), dependencies,
hidden and `.gitignore`'d files are skipped, and reading stops at 1000
files / 256 MiB: `ignore`, `hidden`, `glob`, `max_files`, `max_size`,
`files: false` (overview only) — `att.options("file://")`.
`att.from_prompt(text)` attaches the files a prompt names (inside the
current folder; URLs only with `urls=True`).

Options belong to the file type: `print(att.options(".pdf"))` (or
`att --options .pdf`) lists them. The ones that matter most:

| file | option | effect |
|---|---|---|
| pdf, pptx | `pages: 2-4`, `pages: 1,3,-1`, `max_pages: 10` | pages or slides (`-1` = last); cap on pages read (pdf) |
| pdf | `images: true` | page pictures. The default (`auto`) draws pages only for PDFs with no text at all, so **charts, tables drawn as graphics and layout are invisible unless you ask** |
| pdf | `max_dim: 1568`, `image_format: jpeg`, `quality: 80`, `dpi: 200` | page picture size and format (default `auto`: JPEG for scanned pages, PNG for the rest; longest side 2000 px) |
| pdf, images | `ocr: true` | read the text of scans (needs the `ocr` extra). A PDF does it by itself, page by page, for pages with no text layer (the first 50; `ocr: true` for all) |
| xlsx | `sheet: Sales`, `rows: 100` | one sheet; rows per sheet |
| csv, tsv | `rows: 100`, `delimiter: ";"`, `summary: true` | |
| docx, pptx, xlsx | `images: true` | a picture of each page, slide or sheet, numbered like the text (needs LibreOffice; `auto` = only if installed) |
| docx, pptx | `embedded_images: true` | the pictures stored in the file |
| html | `images: true` | inline data-URI pictures |
| doc, ppt, odt, odp, ods | as docx / pptx / xlsx | converted by LibreOffice (a program to install, not an extra) |
| html, web pages | `select: article` | CSS selector |
| html, web pages | `main: false`, `links: true` | whole page instead of the main content; keep link addresses |
| html, web pages | `screenshot: true`, `max_screens: 2` | pictures of the rendered page (`browser` extra + `playwright install chromium`) |
| images | `max_dim`, `rotate: 90`, `image_format`, `quality` | |
| audio | `model: small`, `language: en` | transcription (`audio` extra) |

**A wrong option does not fail.** `[pagez: 1]` or `[pages: 1-x]` prints a
warning, is kept in `a[0]["meta"]["warnings"]`, and the whole file is read
without it. Look at the warnings whenever you set options.

## 3. Failures come back as data

`att()` never raises. A missing or broken file becomes an artifact with empty
text and `meta["error"] = {"code", "message"}`; if nothing checks, the model
receives an empty document and answers anyway. When a failure must stop the
program:

```python
from attachments import AttachmentsError, att

a = att("docs/").raise_for_errors()  # returns a when nothing failed
```

Every file is still read first; the one exception lists all failures
(`e.errors`: `[{"source", "code", "message"}]`, readable `str(e)`) and keeps
every result, good files included (`e.artifacts`). To skip bad files instead:

```python
from attachments import Artifacts

good = Artifacts(x for x in att("docs/") if "error" not in x["meta"])
```

Not errors: a file type with no reader (`meta["note"]`), an empty document,
option warnings. Check `a.text.strip()` or `a.images` when empty input must
also stop you. A `try/except` around `att()` catches nothing.

## 4. Sending files to a model

```python
import anthropic
from openai import OpenAI

a = att("report.pdf[images: true, max_dim: 1568]")
anthropic.Anthropic().messages.create(
    model="claude-sonnet-4-5",  # any vision model
    max_tokens=1024,
    system="You are a financial analyst.",
    messages=a.claude("What do the charts show?"),
)
OpenAI().chat.completions.create(
    model="gpt-4.1-mini", messages=a.openai("What do the charts show?")
)
```

- The content runs: each page's text, then that page's pictures, then the
  question. `interleave=False` gives all text, then all pictures.
- Both return one user message, `[{"role": "user", "content": [...]}]`; the
  system prompt goes in the API's own parameter.
- Any other API (OpenAI Responses, Gemini, LiteLLM, lm15, your own): map the
  neutral parts, never base64-encode or resize pictures yourself:

```python
content = []
for p in a.parts(prompt="What do the charts show?"):
    if p["type"] == "text":  # {"type": "text", "text": ...}
        content.append({"type": "input_text", "text": p["text"]})
    else:  # {"type": "image", "media_type": "image/png", "data": <base64>}
        url = f"data:{p['media_type']};base64,{p['data']}"
        content.append({"type": "input_image", "image_url": url})
OpenAI().responses.create(
    model="gpt-4.1-mini", input=[{"role": "user", "content": content}]
)
```

- Anthropic limits: 32 MB per request (Bedrock 20 MB), 10 MB per picture
  (Bedrock 5 MB), 100 pictures (600 on some models), and at most 2000 x 2000
  px each when a request has more than 20. `claude()` and `openai()` check
  these and raise a `RequestLimitWarning` naming the problem and the fix;
  turn warnings into errors in tests to catch it. Scanned pages are JPEG by
  default (about 0.4 MB a page), so a 20-page scan is a 10 MB request; long
  PDFs: `pages` or several requests.

## 5. Hide file names when they could give the answer away

By default every file is named for the model: a photo is sent as the text
`## tabby_cat.png`, then the picture. For classification, grading, blind
comparisons, anonymised data, or cache keys that ignore names, pass
`sources=False` (it works on `to_text`, `parts`, `claude`, `openai`, `chunk`):

```python
a = att("photos/img_0042.jpg")
messages = a.claude("Which animal is this?", sources=False)  # picture + question only
a.to_text(sources=False)  # print(a) and a.text always show names
```

Names are also in `a.images[i]["name"]` and `meta["source"]`; keep those out
of prompts too.

## 6. Size and token budgets

```python
a.estimate_tokens()  # {'text': 295, 'images': 3200, 'total': 3495}; repr shows it too
```

Rough figures: text is characters / 4; a picture is Claude's count of 28 x 28
pixel patches: up to 4,784 on Claude 4.7 and later (a default page picture is
about 4,000), up to 1,568 on other models (`estimate_tokens(tier="standard")`).
The estimate uses the larger, so budgets hold everywhere; OpenAI counts
differently. `max_dim` lowers **tokens** (`max_dim: 768`: about 600 a page);
`image_format: jpeg` lowers **bytes** (request size, logs); the default `auto`
already uses it for scanned and photo pages, PNG for text pages where it is
sharp and often smaller.

## 7. Text only: prompts, search, RAG

```python
text = a.to_text(sources=False)
chunks = a.chunk(max_tokens=500, overlap=50)  # list[str]; whole pages kept together
doc = att("report.pdf")[0]
pages = [(s["page"], doc["text"][s["start"] : s["end"]]) for s in doc["meta"]["segments"]]
```

`meta["segments"]` marks pdf pages, pptx slides and xlsx sheets with offsets
into `text`. Page and slide segments carry `page` (the same number as
`ImageItem.page`); `label` is for people (a slide's title, a sheet's name):
never parse it for a number. Each chunk starts with `## <name>` unless
`sources=False`.

## 8. Saving, caching, passing between processes

```python
import json

from attachments import Artifacts

json.dump(a.to_wire(), open("cache.json", "w"))  # pictures as base64
a = Artifacts.from_wire(json.load(open("cache.json")))  # equal to the original
```

`json.dumps(a)` fails as soon as there is a picture (raw bytes). The same
file always gives the same output, byte for byte, so a hash of the
`to_wire()` JSON is a stable cache key. Reading is local: nothing is uploaded
unless `configure(service_url=...)` points at an attachments server.

## 9. Command line

```bash
att report.pdf --pages 1-4         # prompt text on stdout
att docs/ --json > docs.json       # the same JSON as to_wire(); exit 1 if every input failed
att --options .pdf                 # options for one file type
att --skill --install              # this skill, for Claude Code, Pi and Codex
```

`attachments-mcp` is an MCP server that lets an agent read files with `att`.

## Mistakes that cost time

- Installing 0.25 (`pip install attachments`) or writing its API.
- Expecting exceptions; sending an unchecked folder to a model.
- Asking about charts without `images: true`.
- Leaving file names in a classification or evaluation prompt.
- Building content blocks, base64 or resizing by hand instead of
  `claude()`, `openai()`, `parts()` and `max_dim`.
- `json.dumps(a)` instead of `a.to_wire()`.
- A mistyped option, which is only a warning.
