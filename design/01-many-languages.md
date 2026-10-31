# Attachments in many languages (TypeScript first)

*Status, 2026-10-31: agreed (npm name `attachments-dev`). Step 1 done for
presenting (`contract/presenting.md`, 951 cases in `contract/cases/`,
Python passing; still to write: sources, routing, the server's API).
Step 2 done: `ts/` passes every case. Next: step 3, `att()`.*

*Earlier: proposal, nothing built. Written after FunctAI's
TypeScript side asked for documents as inputs (functai conversation
`01a191d5`, and `functai/design/13-files-and-attachments.md`, "when demand
pulls"). It follows the way lm15, lmcc and FunctAI already work in several
languages; where it departs from them, it says why.*

## What we want

Someone who knows Attachments in Python opens the TypeScript package and is
at home: the same words, the same order, the same results. Only the casing
and the language's own mechanics change.

```python
from attachments import att                     # Python
a = att("report.pdf[pages: 1-4]")
a.claude("Summarize.")
```

```ts
import { att } from "<npm name, decision 1>";     // TypeScript
const a = await att("report.pdf[pages: 1-4]");
a.claude("Summarize.");
```

"Fully like Python" means four things, in this order of importance:

1. **The bytes a model sees are identical.** The same artifacts give the
   same text, the same parts, the same Claude/OpenAI/lm15 messages, the
   same chunks and the same token estimates, byte for byte.
2. **Data crosses both ways.** What one language saves (`to_wire`), the
   other loads (`from_wire`), and the hosted server speaks the same form.
3. **The same input string means the same thing.** `[pages: 1-4]`,
   option names, defaults, warnings and error codes are one definition.
4. **The same API, one name per concept.** The table below.

What it does *not* mean: that TypeScript reads a PDF with the same library,
or gets the same characters out of a scanned page. See *Processors*.

## What the family already decided (and this carries over)

From lm15 (`lm15-contract/playbooks/api-family.md`), lmcc
(`contract/contract/portability.md`) and FunctAI (`design/01-many-languages.md`):

- **The contract is the authority.** When code and contract disagree, the
  code is wrong, Python included. A rule changes in the contract first,
  then in every implementation, in the same commit.
- **Native implementations, not wrappers.** No language calls into
  another. A TypeScript user never needs Python installed.
- **One word per concept; casing follows the language, the word does not.**
  Python `estimate_tokens`, TypeScript `estimateTokens`. JSON keys stay
  `snake_case` everywhere (`bytes_b64`, `meta.segments`), and so do DSL
  option names inside the string (`[max_dim: 1568]`).
- **Async is the language's own.** TypeScript is async where it touches
  files or the network, and nowhere else.
- **A core that is exact, plus declared extensions.** A smaller
  implementation refuses or reports what it cannot do; it never quietly
  substitutes something close.
- **Error codes are pinned, messages are not.**
- **Data every language must reproduce lives in the contract as JSON**;
  each implementation carries a copy and a test that the copy is equal.
- **Every deviation is written down** in that language's README under
  *Where TypeScript differs, stated*.

## The one real difference from FunctAI: processors

FunctAI's whole job can be written natively in every language. Attachments'
job splits in two:

| layer | what it does | can it be exact across languages? |
|---|---|---|
| **The pure layer** | DSL, options, the Artifact, wire form, rendering (text, parts, Claude/OpenAI/lm15 messages), chunks, token estimates, the `Artifacts` object, errors | **yes, byte for byte**: it is plain code over plain data |
| **Sources** | files, folders (ignore rules, secrets, sort order, the folder overview), zip/tar, URLs, GitHub, prompt mentions | **yes** for what is chosen and in which order; the overview text too |
| **Processors** | turning a PDF, Word file, workbook, slides, web page, image, audio into an Artifact | **no.** Python's quality comes from PyMuPDF, pypdf, LibreOffice, RapidOCR, faster-whisper. JavaScript has good libraries for some formats and nothing comparable for others |

So the processors follow lmcc's rule "core plus declared extensions", and
Python's own routing rule, which already exists:

> A local processor that lacks what it needs returns a `missing-dependency`
> artifact (or `missing_part` when only the pictures are missing). If a
> service is configured, core sends the file there. (`contract/IR-CONTRACT.md`,
> *Routing contract*)

TypeScript keeps that rule unchanged. A format JavaScript reads well is
read locally; a format it cannot read is exactly like a Python install
without that extra: a `missing-dependency` artifact whose message says what
to install, and, if a service is configured, the hosted or self-hosted
server answers instead. **TypeScript with no optional packages behaves like
`pip install attachments` with no extras.** That is the same behavior
users already know, not a new mode.

Processors are held to two kinds of checks:

- **Structure, exact.** Kind, segments and their offsets matching the text,
  page numbers on segments and images, page selection keeping the
  document's numbers, error codes, warnings for unknown options. These are
  rules, so they are cases.
- **Quality, a floor.** Each format has a shared corpus of real documents
  with known text (not Python's output: the olmOCR-bench pages and the
  `evals/compare/` documents are the start). Each implementation's score on
  it is reported, and a processor ships in a language only when it passes
  the floor, as FunctAI lets a language bake only once it passes the gate.
  Python is measured by the same corpus.

Candidate JavaScript libraries, to be measured against that corpus, not
trusted: PDF text and pictures `pdfjs-dist` (pictures in Node need a canvas
package); Word `mammoth`; workbooks `exceljs`; PowerPoint text by reading
the slide XML (`fflate` for the zip); web pages `@mozilla/readability` and
`turndown`; images `sharp` in Node, canvas in a browser. No local OCR,
audio or Office-to-picture in TypeScript at first: those go to the service.

## The contract: what it fixes

`contract/` becomes the contract (renamed `contract/` or kept as `contract/`,
decision 4). What exists and what is missing:

| area | exact? | today | still to write |
|---|---|---|---|
| Artifact shape, error codes, wire form | yes | `IR-CONTRACT.md`, `artifact.schema.json` | cases: wire round trips, refused wire data |
| DSL grammar and parsing | yes | `dsl-grammar.md`, 37 vectors | cases for `format_dsl` and round trips |
| Options: names, types, defaults, which format declares which | yes | `dsl-schema.json`, written by Python | cases for coercion, unknown-option warnings ("did you mean") |
| Rendering: `to_text`, `parts`, `claude`, `openai`, `lm15`, `sources=False`, interleaving by page | yes | Python tests and doctests only | **cases: artifacts in, exact output out** (the most important ones) |
| `chunk` and `estimate_tokens` | yes | Python tests | cases, including image sizes read from file headers |
| Sources: folders, ignore files, secrets, limits, order, the overview artifact | yes, given the same files | Python tests | cases with small fixture trees |
| Prompt mentions (`from_prompt`) | yes | Python tests | cases |
| Routing: local, service, fallback, `prefer` modes, `meta.via` | yes, with a fake service | Python tests | cases |
| The server's HTTP API (`/process`, `/unpack`, `/formats`, `/options`, `/health`, the `/v1` prefix) | yes | `server.py` | **a written spec**: today the code is the only definition |
| Watermarks on images | meaning only | Python | stated rule, pixels not pinned |
| Processors | structure exact, quality a floor | Python tests, `evals/compare/` | the per-format corpus and floor |

**Where the expected outputs come from.** FunctAI's rule is that cases are
written from the rules by a script, never copied from an implementation.
For rendering, the honest first step is lm15's: draft expected outputs from
Python, mark them `draft`, and have each one read and approved before it
counts as `reviewed`. That is a trade-off: until reviewed, a Python bug
could become the contract. Rendering rules are short enough that the
drafts can be reviewed quickly.

**Who writes the options file.** Python's processors declare their options
in code and `scripts/gen_dsl_assets.py` writes `dsl-schema.json`. Turning
that around (the file declares, Python reads it) would be a large change
for no user benefit. Proposal: the committed file is the contract; Python
keeps writing it, a test already fails when the two differ, and a change
to it is a contract change that TypeScript must follow in the same commit.
TypeScript generates its option types from the file
(`ts/src/generated/`), as FunctAI's TypeScript does from its contract.

## The API, Python and TypeScript

Moved to `02-typescript-api.md`, which also changes two things this note
first proposed: option names keep the contract's spelling (`max_dim`, not
`maxDim`), and bytes in hand are a `File` or `Blob`, not a `Uint8Array`
with a `filename` option.

## Where TypeScript differs, stated

- **`att()` returns a promise.** Reading files and fetching URLs are
  asynchronous in JavaScript. Everything after it (`text`, `parts`,
  `claude`, `chunk`, …) is synchronous, as in Python.
- **Processors may be async**: `(data, { filename, ...options }) =>
  Artifact | Promise<Artifact>`. Most JavaScript readers are.
- **No decorators.** TypeScript decorators work on classes only, so
  `processor({...})` and `source({...})` take one object.
- **Optional packages instead of extras.** `pip install attachments[pdf]`
  becomes "install `pdfjs-dist`" (optional peer dependencies, loaded only
  when a file needs them). The `missing-dependency` message names the npm
  command, so the remedy text is per language while the code is shared.
- **In a browser** there is no file system: inputs are URLs (subject to
  CORS), `Blob` or `File`. Folders, archives and `from_prompt` with
  a `root` are Node (and Deno, Bun) only and refuse with a clear message in
  a browser.
- **Not in TypeScript:** the `att` command line program, the MCP server,
  the HTTP server and the agent skill stay Python's. A second `att` command
  on the same machine would fight over the name; the server is what
  TypeScript calls, not what it ships.

## Repository layout

Proposal: TypeScript goes into this repository as `ts/`, beside Python,
as FunctAI does. The contract still changes with the code (the server API
and rendering cases do not exist yet), and one repository lets a rule and
both fixes land in one commit. lm15 split into one repository per language
only after its contract froze.

Python stays where it is (`src/`, root `pyproject.toml`) rather than
moving into `python/` like FunctAI. Moving it would touch the PyPI
workflow, CI, the deploy scripts on lambda and the skill links in
`~/.claude`, `~/.pi` and `~/.codex`, for tidiness only. The cost: the
layout makes Python look like the authority, which it is not. The
contract's README says so plainly.

```
contract/ (or contract/)   the authority: rules, schemas, cases, corpus list
src/attachments/       Python (PyPI attachments)
ts/                    TypeScript: src, src/generated, tests, README, CHANGELOG
check                  one command: the contract, Python, TypeScript
```

Each language keeps its own version and tag (`v1.0.1` stays Python's,
TypeScript tags `ts-v0.1.0`), and states which contract formats it reads
and writes.

## Order of work

1. **Contract first, with Python passing it.** Rendering cases (the most
   important), wire cases, DSL format cases, option cases, sources cases,
   routing cases with a fake service, the server API written down. Python
   must pass all of them before TypeScript starts; any Python bug found on
   the way is fixed in Python.
2. **TypeScript pure layer**: the Artifact, wire form, DSL, options,
   rendering, chunks, tokens, errors, the `Artifacts` object. Passes every
   exact case. At this point TypeScript can already load what Python saves
   and do everything after `att()`.
3. **TypeScript sources and routing**: files, folders, URLs, the service
   client. With a service configured, every format now works.
4. **Text-like processors** in TypeScript: text, code, Markdown, CSV, JSON,
   notebooks, SVG as text. Exact cases.
5. **Native processors one format at a time**, each shipping only when it
   passes its quality floor: likely web pages, Word, workbooks, PDF text,
   then PDF pages as pictures.
6. **FunctAI TypeScript** takes Attachments values, through the same lmcc
   binding Python uses.

Steps 1 to 3 are what makes it "fully like Python". Step 5 is open-ended
by design, as lm15 and lmcc leave their long tails open.

## Decisions for Maxime

1. **The npm name.** See `02-typescript-api.md`, decision 1: the
   `@attachments` scope turned out to belong to someone else.
2. **Do we commit to native processors (step 5) or stop at step 4?**
   Steps 1 to 4 give the same API everywhere, with the service doing the
   heavy formats. Step 5 is what lets a browser or a private Node app read
   a PDF with no server. Recommendation: commit to steps 1 to 4 now, and
   to step 5 per format once the corpus says a JavaScript library is good
   enough.
3. **Bytes as input in Python too.** A browser has no paths, so
   TypeScript needs `att(bytes, filename=)`. By the contract-first rule it
   goes into Python as well (it is useful there: uploads, databases).
   Recommendation: yes, in both.
4. **`contract/` or `contract/`.** The family says `contract/`; this
   repository and its docs say `contract/`. Renaming touches links in docs,
   the skill and tests. Recommendation: rename, once, in step 1.
5. **Who approves drafted cases.** Rendering cases drafted from Python
   need a person (or a separate, careful review) to read them before they
   count. Recommendation: you approve the rendering cases; the others can
   be reviewed by an agent that did not draft them.
