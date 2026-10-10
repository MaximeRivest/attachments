# How well do coding agents use attachments?

`run.py` gives each of 20 tasks to a fresh Pi agent in a fresh workspace and
grades the result by code (never by asking a model). Every agent gets the
same two skills: attachments' own (`src/attachments/skill/`) and lm15's, as
published at https://lm15.dev/skill.md. Tasks that call a model use
`openai-codex:gpt-6-luna` through lm15, whatever the agent's model, so the
score measures the agent's work.

| # | task | what the agent must do | the trap |
|---|---|---|---|
| 1 | `photos` | Claude request bodies naming the animal in 6 photos | the file names are the answers |
| 2 | `charts` | OpenAI messages to read charts on pages 3-5 | charts are invisible without `images: true` |
| 3 | `folder` | a folder to a reloadable JSON cache; stop and name unreadable files | `att()` never raises; JSON cannot hold bytes |
| 4 | `install` | an empty uv project: print pages 2-3 | `uv add attachments` installs 0.25 |
| 5 | `scans` | one Claude request reading a 40-page scan | 32 MB request limit (fixed by the library since: JPEG scans) |
| 6 | `sheet` | the text of a 5,000-row sheet, nothing else | 200 rows by default |
| 7 | `cache` | an lm15 `Request` whose handbook is a cacheable prefix | where the cache mark goes |
| 8 | `providers` | one lm15 `Request` for Anthropic, OpenAI and Gemini, with chart pages | pictures in all three |
| 9 | `labels` | slide pictures that show their own slide number | `watermark: page` |
| 10 | `rag` | ≤1000-character chunks, each from one page, with its page number | `chunk()` gives no page numbers |
| 11 | `secrets` | a project for an outside reviewer | a private key in a file with no telling name |
| 12 | `invoices` | totals of 6 invoices (2 scanned), asked of a model | scans need OCR or pictures |
| 13 | `chart_values` | the top region per quarter, read from chart pictures | numbers only in pictures |
| 14 | `contracts` | what changed between two Word contracts | a change inside a table |
| 15 | `web` | a price from a web page | a decoy price in the banner |
| 16 | `repo` | a default value from a git repository | a stale copy in an ignored `build/` |
| 17 | `mcp_pdf` | MCP tools only: a fact on page 27 of 40, and its page | the whole PDF is cut in the middle by the client |
| 18 | `mcp_folder` | MCP tools only: which files a folder read leaves out | read the overview |
| 19 | `cli_json` | `att` only: pages 2-3 with pictures, as loadable JSON | the wire format, page pictures |
| 20 | `cli_web` | `att` only: a web article as Markdown, no menus | main content, tables |

`--check` runs a hand-written expert solution (must score 1.0) and a naive
one (must fail) per task before any agent is graded; all 40 behave, except
the naive `scans`, which the library now gets right by itself.

```bash
uv run python evals/bench/run.py --check
uv run python evals/bench/run.py --reps 3 --parallel 6
uv run python evals/bench/run.py --report evals/bench/runs/<stamp>
```

## Results (2026-10-10, commit 2c28a3d, thinking medium, 3 runs per cell)

| task | gpt-6-luna | gpt-6.1-sol |
|---|---|---|
| photos | 3/3 (12 s) | 3/3 (23 s) |
| charts | 3/3 (13 s) | 3/3 (27 s) |
| folder | **1/3** (31 s) | 3/3 (67 s) |
| install | 3/3 (16 s) | 3/3 (38 s) |
| scans | 3/3 (215 s) | 3/3 (38 s) |
| sheet | 3/3 (21 s) | 3/3 (42 s) |
| cache | 3/3 (34 s) | 3/3 (60 s) |
| providers | **2/3** (14 s) | 3/3 (41 s) |
| labels | 3/3 (41 s) | 3/3 (49 s) |
| rag | 3/3 (22 s) | 3/3 (44 s) |
| secrets | 3/3 (27 s) | 3/3 (39 s) |
| invoices | 3/3 (42 s) | 3/3 (67 s) |
| chart_values | 3/3 (27 s) | 3/3 (61 s) |
| contracts | 3/3 (31 s) | 3/3 (56 s) |
| web | 3/3 (28 s) | 3/3 (38 s) |
| repo | 3/3 (31 s) | 3/3 (35 s) |
| mcp_pdf | **0/3** (30 s) | 3/3 (20 s) |
| mcp_folder | 3/3 (21 s) | 3/3 (12 s) |
| cli_json | 3/3 (17 s) | 3/3 (19 s) |
| cli_web | 3/3 (18 s) | 3/3 (22 s) |
| **total** | **54/60** | **60/60** |

Median time a run: Luna 25 s, Sol 39 s; about 7 tool calls either way. The
attachments skill was read in 103 of 120 runs, lm15's in 58.

What the failures say:

- **`mcp_pdf` (Luna 0/3): the MCP tool is hard to use on long documents.**
  The whole 40-page PDF is ~14k tokens; Pi cuts the middle of any result
  over 20 KB, so page 27 never arrives. Luna asked again for pages 1-40,
  then 1-20 (also cut), then gave up. Sol asked for small ranges (1-4,
  5-24, 25-34) and found it. The tool's output has no page markers, and
  nothing tells the agent to read a long document in ranges.
- **`folder` (Luna 1/3): `images: true` on a whole folder fails Word and
  Excel files when LibreOffice is missing.** Luna asked for pictures of
  everything; without LibreOffice each .docx/.xlsx became an *error* (text
  lost), so the script refused to save. A picture that cannot be made
  could instead be a warning on a file whose text was read.
- **`providers` (Luna 1 miss): the agent said "I'll create ask.py" and
  stopped.** A model slip, not a library one.
- **`secrets`: all 6 agents left the private key out**, by noticing
  `deploy_key` in the folder overview and adding `ignore:`. The library
  itself skips secrets by file name only, so a key in a file with a
  neutral name is sent unless someone looks.
- The lm15 tasks (7-16) all passed: `a.lm15()` and the attachments skill
  were enough, with lm15's own skill read in half the runs.

## After the fixes (2026-10-10, commits a39cdec and b637f8c)

The three library problems above were fixed: the MCP tool marks pages and
returns long results in parts with a note on how to go on; pictures that
cannot be drawn are a warning, never at the cost of the text; files that
start like a private key are skipped whatever their name. Same 20 tasks,
same models, 3 runs each:

| | gpt-6-luna | gpt-6.1-sol |
|---|---|---|
| total | **60/60** (was 54/60) | **60/60** |
| folder | 3/3 (was 1/3) | 3/3 |
| mcp_pdf | 3/3 (was 0/3) | 3/3 |
| providers | 3/3 (the earlier miss was a model slip) | 3/3 |

On `mcp_pdf`, Luna first asked for `max_chars: 30000`; Pi still cut the
middle out and it found page 27 by luck. Since b637f8c the server's limit
holds (`max_chars` can only lower it; `ATTACHMENTS_MCP_MAX_CHARS` sets it):
rerun 6/6 for both models, Luna reading pages 1-11, 12-22, 23-34 with
nothing cut.

Building this benchmark also found a bug, fixed in 2344936: PyMuPDF 1.28
(what a fresh install gets) printed an advert on standard output from its
table finder, which broke `att --json > file`.
