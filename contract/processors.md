# Processors every implementation has (v1)

The formats an implementation reads exactly as Python does, with no
dependency: text ([reading.md](reading.md#the-text-processor)), CSV,
Jupyter notebooks and SVG (its text). Other formats are measured by
quality against a corpus, not pinned here (`design/01-many-languages.md`).
The cases are in `cases/processors.json`; text, lengths and offsets
follow [README.md](README.md#text-numbers-and-white-space).

A processor never throws for a bad file: it returns `parse-error` (the
message is not pinned). A processor that crashes on data it did not
expect (a notebook whose `metadata` is a list) gives what any crash gives:
`processing-error`.

## CSV (`.csv`, `.tsv`)

Options: `rows` (aliases `max_rows`, `limit`; default 200), `delimiter`
(alias `sep`), `summary`.

1. Decode as the text processor does. Only white space: an empty artifact,
   kind `table`, note `empty CSV`, extra
   `{"rows": 0, "encoding", "engine": "stdlib"}`.
2. **The delimiter**: the `delimiter` option, if given: `tab`, `comma`,
   `semicolon`, `pipe` (any case, trimmed) or its first character. Else
   the delimiter CPython's newest
   `csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")` finds (patch
   releases 3.11.17, 3.12.15, 3.13.16 and 3.14 changed it), carried by
   each implementation instead of taken from its language's library
   (Python: `_processors/_sniffer.py`), so an older Python guesses the
   same: line breaks normalized to `\n` first; its regular expressions
   with Python's `^`/`$` in multiline mode, which see only `\n` as a
   line break, and Python's `\w`; a quoted field's body ending at the
   first quote that is not doubled; its frequency tables, ties broken by
   first seen; its 0.01 steps from 1.0 down to 0.9; the preferred order
   `, \t ; space :`. When it finds none:
   tab for a `.tsv` name, else comma.
3. **Rows**: Python's `csv.reader` with that delimiter and every other
   setting of the `excel` dialect (`"` quotes, doubled to escape, not
   strict), reading the text as lines ending in `\n`, `\r\n` or `\r`
   (`io.StringIO(text, newline="")`, as the `csv` documentation asks).
   Its state machine
   is the rule: a quote inside an unquoted field is a character; text after
   a closing quote joins the field; a line break inside quotes is kept;
   an unterminated quote runs to the end; an empty line is an empty row.
4. The first row is the header; the rest are data rows, of which the
   first `rows` are shown. Each cell has `\r\n`, `\n`, `\r` replaced by a
   space and `|` by `\|`. Text: `| h1 | h2 |`, `| --- | --- |`, then one
   line per row, `| ` + cells joined by ` | ` + ` |`, rows not padded.
5. Meta: kind `table`, extra `{"rows": data rows, "cols": header cells,
   "delimiter", "encoding", "engine": "stdlib"}`, plus
   `"rows_truncated": true` when rows were left out. `summary: true`
   adds a summary where the implementation has one (Python, with pandas);
   without it the table comes back with a warning naming what is missing.

## Jupyter notebooks (`.ipynb`)

Options: `outputs` (default false), `watermark`.

1. Decode UTF-8 (invalid bytes replaced) and parse as JSON as Python's
   `json.loads` does: `NaN`, `Infinity` and `-Infinity` are accepted; a
   byte order mark is an error. Not JSON, not an object, no `cells`
   (with a message about nbformat 3 when there is `worksheets`), or
   `cells` not a list: `parse-error`.
2. Language: `metadata.language_info.name`, else
   `metadata.kernelspec.language`, else `python` (an empty value counts as
   missing).
3. Each cell (a cell that is not an object is an empty one), numbered from
   1: its source is a list of lines joined, a string, or `""` when absent.
   A `code` cell is ` ```LANGUAGE\nSOURCE\n``` `; with `outputs`, then
   each output's text as ` ```output\nTEXT\n``` `, joined by a blank
   line. An output's text: `stream` its `text`; `execute_result` and
   `display_data` their `data["text/plain"]`; `error` its `traceback`
   lines joined by `\n`; each with leading and trailing `\n` removed,
   skipped when empty, and when longer than 2,000 characters cut to the
   first 2,000, white space removed at the end, plus `\n… (truncated)`.
   With `outputs`, each `data["image/png"]` (base64, lines joined; ignored
   when it does not decode) is a picture named
   `STEM-cell-N-output.png`, then `-2`, `-3`… for more in that cell
   (`STEM`: the file name without `.ipynb`). A `markdown` cell is its
   source; anything else is `raw`, its source.
4. Cells are joined by a blank line. One segment per cell: kind
   `section`, label `cell N (code|markdown|raw)`, its offsets.
5. Meta: kind `notebook`, extra
   `{"cell_counts": {"code", "markdown", "raw"}, "language", "nbformat"}`
   (`nbformat` as given, 4 when absent).

Values that are not text (a number as a cell's source) are written as
Python writes them (`str`).

## SVG (`.svg`, `.svgz`)

Options: `images` (alias `render`; default false), `watermark`.

1. Gzip (by the `1F 8B` start or a `.svgz` name) is decompressed; a
   failure is `parse-error`.
2. Parsed as XML 1.0 with namespaces, as Python's `ElementTree` with
   expat parses: a document that is not well-formed is `parse-error`
   (an XML declaration other than `version`, then optional `encoding`
   and `standalone`, with a version of `1.` and digits; unclosed or
   mismatched tags, text or a second element after the root,
   an undefined entity, a reference to an external entity, an invalid
   character or character reference, a duplicate attribute, an unbound
   prefix, an XML declaration not at the very start, an unknown encoding).
   Python's verdict comes from the expat library its build ships with:
   expat before 2.7 also accepts a version of any letters, digits, `.`,
   `_` and `-` (even empty), so no case pins those.
   The encoding is UTF-8, UTF-16 by its byte order mark, or the
   declaration's (ISO-8859-1 and US-ASCII as defined, others as Python
   names them). Line breaks are normalized to `\n`; entities declared in
   the document's own DTD are expanded; comments and processing
   instructions are dropped (text on both sides of one is joined); CDATA
   is text. Attribute values have each literal tab and line break turned
   into a space.
3. Text: in document order, each element whose local name (namespace
   removed) is `title`, `desc`, `text`, `tspan` or `textPath`, and that is
   not inside one already taken, gives one line: its text pieces (its own
   text, then each descendant's text and the text after each
   descendant), each stripped, the non-empty ones joined by a space; empty
   lines are dropped. Lines are joined by `\n`.
4. Meta: kind `vector`, extra: the root's `width`, `height` and `viewBox`
   attributes when present, `elements` (every element, the root
   included), `has_text`, and `compressed: true` when it was gzip.
5. `images: true` (or `always`) asks for a PNG of the drawing; an
   implementation without a renderer keeps the text and records the
   missing part (`missing_part`), so the service draws it when one is
   configured. `auto` draws only when it can, and otherwise records
   `extra.render_skipped`.
