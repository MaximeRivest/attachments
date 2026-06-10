# Attachments — Vision

> **Turn anything into LLM-ready context, in one line, in any language.**

## The job to be done

Developers building with LLMs constantly need the same thing: *"I have a thing
(file, directory, URL, repo, spreadsheet…) — give me text + images I can put in
a prompt, without installing and learning five parsing libraries."*

Attachments is the community funnel for that job. The value is:

1. **A corpus of converters** — every format, every source, maintained once.
2. **One standard output shape** — the **Artifact** — that every converter
   produces and every consumer (prompt builders, RAG pipelines, agents) accepts.
3. **One delightful one-liner** — `att("report.pdf[pages: 1-4]")` — identical in
   spirit across Python, TypeScript, and beyond.

## Strategy in one paragraph

**Win Python first; everything else follows from the server.** Adoption comes
from `att("x.pdf")` just working, broad format coverage, and a delightful DSL —
not from a spec. The Artifact IR is frozen as a lightweight *discipline* (one
page of schema + invariants enforced in CI), not a standards effort. The
self-hosted server is the wedge for both the polyglot story (a thin client in
any language is ~a week of work once the server exists) and the eventual
platform (the hosted backend is the server plus keys, billing, and heavy
machinery like OCR/transcription that nobody wants to install locally).
Because local and hosted emit the same Artifact, upgrading from the free
library to the paid platform is one `configure()` line — the library is the
funnel, and it stays free and excellent forever.

## The core bet: standardize the artifact, not the pipeline

Earlier versions of attachments bet on an elegant composition grammar
(`load | modify | present | adapt`). That grammar is clever, but it is not the
value proposition, it is hard to port across languages, and it raises the bar
for contributors. **The project's center of gravity is a small,
language-neutral protocol:**

```
{ text, images[], audio[], video[], meta }     # the Artifact IR
```

connected by **two orthogonal registries**:

| Registry | Question | Examples |
|---|---|---|
| **unpack handlers** | *WHERE does it come from?* | local path, dir, zip, `https://`, `github://`, `s3://` |
| **processors** | *WHAT is it?* | `.pdf`, `.xlsx`, `.docx`, `.html`, code, images |

`unpack()` flattens any source into `(filename, bytes)` pairs; a processor is a
**pure function `(bytes, options) -> Artifact`**. Source × format multiply:
every new source works with every format, and vice versa.

**How contributors plug in:** write one pure function `(bytes, options) ->
Artifact`, declare its option schema, add golden fixtures. That's the whole
contract. The pipeline machinery (routing, fallback, DSL parsing, transport)
is our job, not yours.

### What the IR does and does not promise

Be precise here, because it shapes the conformance suite:

- **Truly portable (byte-identical across implementations):** the Artifact
  schema, the typed `meta` envelope, error typing, and the DSL grammar with
  its parser test vectors.
- **Not portable (and we don't pretend otherwise):** extraction *content*.
  Different engines (pypdf vs. a JS PDF library) produce subtly different
  whitespace, hyphenation, and ligatures. Cross-implementation conformance
  therefore checks **structural invariants** (shape, keys, option handling,
  error behavior); content golden fixtures are **per-backend**.
- **Fidelity trade-off:** `{text, images}` is deliberately simple. The escape
  valve for RAG users is optional structural segmentation (pages/sheets/
  sections with offsets into `text`) — richer layout models are out of scope.

**Anti-goal: spec-itis.** The IR freeze is ~a week of work (one-page schema,
invariants in CI, DSL test vectors), not a quarter. A spec with no adoption is
worth zero; a popular library can always tighten its spec later.

## The DSL: small, specified, delightful

The DSL is the user-facing soul of the project, so it gets its own rules.

### Syntax (the whole grammar)

```
source[key: value, key2: value2, ...]
```

- **Values:** numbers (`300`), booleans (`true`/`false`), ranges (`1-4`,
  `1,3-5,-1`), bare strings (`Sales`), quoted strings when needed.
- **That's it.** No nesting, no expressions, no operators. If an option can't
  be expressed as `key: value`, it belongs in code, not in the DSL.

### Principles

1. **The DSL is sugar, never the only way.** Every DSL option has an identical
   keyword-argument twin: `att("doc.pdf[pages: 1-4]")` ≡
   `att("doc.pdf", pages="1-4")`. Explicit kwargs override DSL.
2. **Options belong to processors, not to a central table.** Each processor
   *declares* its option schema (name, type, aliases, default, docstring).
   The cheatsheet, the validation, the error messages, and the autocomplete
   data are all **generated** from these declarations. Adding a processor never
   means editing core.
3. **Errors teach.** An unknown key never fails silently:
   `Unknown option 'sheets' for .xlsx — did you mean 'sheet'?` An unused key
   warns. A type mismatch shows the expected form with an example.
4. **One grammar everywhere.** The DSL grammar lives in the spec with shared
   test vectors; every language port parses it byte-for-byte identically.

### Testability

- The parser is a pure function `string -> (source, options)` with a published
  test-vector file (input string → expected JSON) used by every implementation.
- Every declared option ships with at least one golden fixture proving its
  end-to-end effect (e.g. `pages: 1-2` yields a 2-page artifact).
- Round-trip property: `format(parse(s)) == normalize(s)`.

### Autocompletion & discoverability (Python first)

We pursue three layers, cheapest first; all are generated from the same
processor option schemas:

1. **Runtime discoverability (now).** `att.options(".pdf")` prints the option
   table; `att.options()` lists everything. Rich "did you mean" errors make the
   REPL itself the documentation. *Cheap, works everywhere, ships first.*
2. **Static typing surface (now).** Generated `TypedDict`s / `Literal` aliases
   and overloads in type stubs so the kwarg form (`att("f.pdf", pages=...)`)
   autocompletes in any editor with no plugin. *Free for users; limited to the
   kwarg twin, since strings are opaque to type checkers.*
3. **Editor extension / LSP (later, the delightful one).** A small VS Code
   extension (and ideally a generic LSP server) that recognizes the
   `[...]` DSL inside string literals passed to `att()` and offers completion,
   hovers, and squiggles — powered by a `dsl-schema.json` exported by the
   library, so it is language- and version-agnostic.

**The pick:** do 1 + 2 immediately — they cover most of the delight at ~5% of
the cost, and they force the option-schema infrastructure into existence. Build
3 once the schema export is stable, because it reuses that exact artifact and
one extension then serves Python, TypeScript, and every future port. What we
explicitly do *not* do: invent a clever in-Python builder API as a substitute
for the DSL — two ways to spell options is the maximum.

---

## Roadmap (epics → stories → sprints)

"Done" means: the Python library is undeniable (coverage + DX), the IR is
frozen and CI-enforced, the server runs in production, one non-Python client
passes conformance — with an intentionally **open long tail of processors and
sources** that the community fills in forever.

Ordering principle: **adoption funds everything**. Python dominance first, IR
freeze as cheap insurance alongside, server as the wedge, polyglot and
platform only when pulled by demand.

### Epic A — Python dominance (the 90%)
- **A1.** As a user, `att(anything)` just works for the formats v1 already
  handled: port the v1 corpus (pptx, images, repos polish) into pure
  `(bytes, options) -> Artifact` processors.
- **A2.** As a user, I feel the DSL: rich errors ("did you mean", unused-key
  warnings), `att.options()` runtime discovery, generated cheatsheet.
- **A3.** As a user, content is detected by magic bytes when the extension
  lies or is missing.
- **A4.** As a prompt builder, I get the last mile: artifact list → assembled
  prompt string, → Claude/OpenAI message blocks, → token/structure-aware
  chunks.
- **A5.** Ship `1.0.0aN` pre-releases to PyPI early and often; `1.0` when
  A1–A4 are green.

### Epic B — IR freeze (one week, alongside Epic A)
- **B1.** One-page versioned JSON Schema for `Artifact` with a typed `meta`
  envelope (`source`, `kind`, `error{code,message}`, provenance, truncation —
  no free-form flag soup), validated in CI on every processor and server
  response.
- **B2.** Typed missing-dependency signals (no error-message string matching)
  driving local/service fallback.
- **B3.** DSL grammar spec + parser test vectors (the truly portable part).
- **B4.** Optional structural segmentation (pages/sheets/sections with
  offsets) so RAG consumers never re-parse.
- **B5.** Conformance runner: structural invariants cross-implementation,
  content goldens per-backend.

### Epic C — Processor author experience
- **C1.** Declared option schemas per processor; docs/validation/autocomplete
  generated from them.
- **C2.** Generated typing stubs for kwarg autocomplete.
- **C3.** Contributor playbook: pure function + option schema + golden
  fixtures = mergeable PR.

### Epic D — The server (wedge for polyglot AND platform)
- **D1.** As a zero-deps user, configuring a key/URL transparently processes
  via service; `prefer=` controls local/service/only modes.
- **D2.** As a team, I run `attachments-server` (Docker, systemd, CI recipes)
  exposing the full processor corpus.
- **D3.** As an operator, the server enforces auth, size limits, timeouts,
  and returns schema-valid artifacts (CI-checked against Epic B).

### Epic E — Polyglot (pulled by demand, not pushed)
- **E1.** TypeScript thin client (DSL parser + trivial unpack + service
  backend) passing structural conformance. Build when the first real demand
  signal appears; it's ~a week once Epic D exists.
- **E2.** Native TS processors for top formats only if usage proves out;
  document the porting playbook.
- **E3.** VS Code DSL extension powered by `dsl-schema.json` (serves every
  language at once).

### Epic F — Platform (open-core, after the funnel exists)
- **F1.** Hosted backend = `attachments-server` + API keys + billing + heavy
  machinery (OCR, transcription, layout models) nobody wants locally.
- **F2.** Onboarding is one line: `configure(api_key=...)` — same Artifact
  out, by construction.
- **F3.** The local library remains free and excellent forever; the platform
  sells convenience, scale, and heavy compute — never basic functionality.

### Epic G — The long tail (never "done", by design)
- Community processors (eml, audio transcription, …) and unpack handlers
  (`s3://`, `gdrive://`, `notion://`, …), each landing as: pure function +
  option schema + golden fixtures. Curated tiers: core / verified / community.

### Sprint shape (2-week sprints, suggested order)

| Sprint | Goal | Mainly |
|---|---|---|
| 1 | Port v1 corpus (pptx, images, repos); magic-byte routing | A1 A3 |
| 2 | IR freeze: schema + typed errors + DSL vectors, CI-enforced | B1 B2 B3 |
| 3 | Option schemas; rich DSL errors; `att.options()`; cheatsheet | C1 A2 |
| 4 | Last mile (render/adapt/chunk); typing stubs; `1.0.0aN` out | A4 C2 A5 |
| 5 | Server hardened + recipes; segmentation; conformance runner | D2 D3 B4 B5 |
| 6 | `1.0` release; contributor playbook; community onboarding | A5 C3 G |
| 7+ | Pulled by demand: TS client, VS Code ext, platform alpha | E F G |

---

## Non-goals

- A composition grammar / operator-overloaded pipeline as public API.
- Spec-itis: standards work beyond the one-page schema + test vectors.
- Pre-building N language clients before a server exists and demand pulls.
- Being a document *understanding* product (OCR models, layout ML) — we route
  to such tools; we don't build them.
- More than two ways to pass an option (DSL string and kwargs — that's all).
- Aspirational docs: nothing appears in README/docs unless it runs today.

## Where things stand

**This repo IS attachments 1.0.0** — the next major version of the
[`attachments`](https://pypi.org/project/attachments/) PyPI package. Epics
A–D are substantially complete: the IR is frozen and CI-enforced by a
conformance suite (`spec/` + `tests/test_conformance.py`), processors declare
option schemas with `att.options()` runtime discovery and "did you mean"
errors, the v1 corpus is ported through pptx and images with magic-byte
routing, and the server plus the render/adapt/chunk last mile ship. The 0.x
grammar API is a clean break — see [CHANGELOG.md](CHANGELOG.md) for the
migration pointer.

- **Next:** `1.0.0aN` pre-releases to PyPI (stable users on
  `pip install attachments` are never affected — pip ignores pre-releases by
  default), then `1.0` proper.
- **v1** (the original `attachments` repo, published as 0.25.x on PyPI) is in
  **maintenance mode**: bug fixes only, no new features. It remains the
  richest corpus of converters; the long tail (OCR, audio, `s3://`,
  `gdrive://`, ...) stays open by design (Epic G).

Work here without looking at v1/v2 — everything you need is this repo plus this
document.
