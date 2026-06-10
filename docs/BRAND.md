# attachments — brand

> The brand lives in the code: in reprs, error messages, docstrings, and
> READMEs — long before it lives on a website. This document versions
> alongside the code it describes. PRs that touch user-facing words (errors,
> hints, README copy, site copy) should be checked against it the same way
> code is checked against `spec/IR-CONTRACT.md`.

---

## 1. Positioning

One sentence; every other decision derives from it:

> For anyone putting files in front of an LLM — data scientists,
> researchers, analysts, developers — **attachments** is the **context
> layer**: it turns any file, folder, URL, or repo into model-ready
> artifacts, locally when your machine can, hosted when the job is heavy —
> unlike services that lock you in, installs that weigh a gigabyte, or
> parsers that hand back shapeless text.

**The category we claim: "the context layer."** Not "OCR as a service,"
not "document parsing," not "a converter library." OCR, transcription, and
captioning are capabilities *inside* the context layer. The category is
unclaimed today (Docling, MarkItDown, unstructured, LlamaParse all circle
it without naming it); we claim it loudly and early or not at all.

**Banned framings:** "OCR as a service" (a feature, not the category),
"ETL for LLMs" (enterprise-speak, wrong audience), "AI-powered" (we are
the layer *under* the AI).

## 1b. Audience

The primary audience is **not** infrastructure engineers. It is the
scientific-computing and data crowd: scientists, R and Julia and Python
data people, analysts, grad students, domain experts — people who have a
file (a scan, a spreadsheet, a folder of microscopy images, a recording)
and a question for an LLM. They:

- **Do not want to know** about file types, encodings, MIME sniffing, or
  how multimodal context must be shaped for an API. That knowledge is our
  job; hiding it is the product.
- **Live in notebooks** — Jupyter, RStudio/Positron, Quarto, Colab — more
  than in terminals. The notebook cell is a first-class brand surface
  (`_repr_markdown_` already renders summaries, error admonitions, and
  thumbnails there; treat that rendering with the same care as the repr).
- **Hit dependency pain fast and bail fast.** A failed
  `pip install onnxruntime` on a locked-down university machine is the
  moment they either find our free hosted tier or leave forever. Errors
  that teach are written for *this* person — assume no terminal fluency,
  give the exact command, offer the hosted path when the install is heavy.
- **Upgrade on need, not on persuasion.** One day they need higher
  quality (real OCR, video captions), higher volume, or a hosted
  guarantee — and only then does paying make sense. Until then, free and
  cheap is the relationship.

Secondary audience: developers building LLM apps and pipelines. They get
the spec, the conformance suite, the self-host story. Write docs so the
primary audience never has to read the parts meant for the secondary one.

**Copy register implication:** plain words before jargon. "Works in your
notebook" before "REPL-friendly repr." "We run it for you" before
"hosted inference endpoint." Never *dumbed down* — precision stays — but
the vocabulary defaults to the reader's world (files, sheets, scans,
recordings), not ours (artifacts, IR, registries). The internal nouns
appear only where the reader needs them.

## 2. Personality

Three traits, one rejection. Every word we ship is tested against these.

| Trait | What it means | Where it already lives |
|---|---|---|
| **Precise** | Frozen one-page contract, typed errors, conformance suite. We say exactly what happens and never more. | `spec/IR-CONTRACT.md`, error codes in `types.py`, `~N tokens` honesty ("a fast chars/4 approximation, not a real tokenizer") |
| **Generous** | Zero required deps, errors that teach, free hosted tier, MIT including the server. We leave the user better off than we found them, especially when something fails. | `"did you mean 'sheet'?"`, the scanned-PDF hint, keyless servers |
| **Honest** | Anti-lock-in as identity. The exit path is documented next to the entrance. | "You can leave at any time", self-host one-liner, "no telemetry, ever" |

❌ **Rejected: salesy.** Never urgent, never FOMO, no exclamation points,
no countdowns, no "upgrade now." The give-first model collapses into
bait-and-switch the moment the brand pushes. The paid tier is *offered*,
exactly once, exactly where it is genuinely the better answer — see §4.

The combined register is **sober tone, generous behavior**: a senior
engineer who never raises their voice but always leaves you better off.

## 3. Verbal identity

### Name

- The product is **attachments** — always lowercase, even at the start of
  a sentence in marketing copy. (Sentence-initial capitalization is
  acceptable in long-form prose where lowercase would read as a typo.)
- The function is `att()`. The CLI is `att`. The hosted endpoint is
  `api.attachments.dev`. The site is `attachments.dev`.
- Never "Attachments.dev" as a product name; the product is the library,
  the service is a convenience attached to it.

### Tagline

- Primary: **"Turn anything into LLM-ready context."**
- Category line (secondary, for headers/social bios): **"The context layer."**
- Never combine them into one sentence; they do different jobs.

### Voice rules

1. **Active voice, second person in docs.** "You call the endpoint," not
   "the endpoint may be called."
2. **No exclamation points.** Anywhere. Including release notes.
3. **Errors state what happened, why, and the fix — in that order.**
   The fix is concrete (`pip install attachments[pdf]`), never "please
   check your configuration."
4. **Show, don't claim.** "Blazingly fast," "powerful," "seamless" are
   banned. Show the repr, show the one-liner, show the error that teaches.
   The reader concludes the adjective themselves.
5. **Numbers are honest.** Token counts are labeled approximations. Costs
   and limits are stated plainly (25 MB, rate-limited, not stored).
6. **Local remedy first, hosted second.** In any message offering both,
   the local path always comes first. Never invert this, even when revenue
   tempts. (See §4.)
7. **The product never compliments itself or the user.** No "awesome,"
   no "great choice."

### Canonical strings

These exact artifacts are brand assets; changing their *shape* is a brand
decision, not a refactor:

- The repr:
  `<Artifacts: 1 artifact | 202 chars | ~51 tokens | 4 images>`
- The teaching error:
  `! missing.pdf: unpack-error — unpack failed: Unsupported or non-existent input: missing.pdf`
- The hint format (what — local remedy — hosted remedy):
  `No text layer (scanned?) - pip install attachments[ocr], or the free hosted tier: attachments.dev`
- The did-you-mean:
  `Unknown option 'sheets' for .xlsx — did you mean 'sheet'?`

The repr appears in every screenshot, social card, talk slide, and example.
It is our code-sample hero, the way Stripe's docs made code samples theirs.

## 4. The HEAVY_FEATURES doctrine

The monetization ethic is already compressed into one frozenset in
`src/attachments/types.py`:

```python
HEAVY_FEATURES = frozenset({"ocr", "audio"})
```

**Brand law: the hosted service is mentioned only where it is genuinely
the better answer.** Concretely:

- A missing-dependency message mentions the hosted tier **only** when the
  local install is genuinely heavy (onnxruntime, whisper weights, future:
  video captioning models, exotic scientific-format toolchains like
  microscopy stacks). Light extras (`pdf`, `xlsx`, `docx`, `html`, ...)
  get the plain `pip install` remedy and nothing else — forever.
- Adding a feature to `HEAVY_FEATURES` is a brand decision and gets review
  against this document, not just a code review.
- The hint appears **once per process feel** (the repr collapses repeats),
  is kept under ~150 chars so the remedy is never clipped, and always
  names the local path first.

Why this is law: the scanned-PDF hint is the highest-converting ad we will
ever run, and it converts *because* it reads as help. The first time it
reads as an ad, the entire give-first model is spent.

## 5. The growth narrative

The brand and the business model must tell the same story, or the paid
tier reads as the catch:

1. **Library** — free, local, zero-dep, delightful. Acquisition surface:
   README, PyPI listing, the repr in screenshots, errors that teach.
2. **Free hosted tier** — covers what is *annoying* to install, not what
   is valuable to sell. OCR, transcription, dependency-hell formats.
   Framing: "we keep the heavy stuff warm so you don't have to." No key,
   no signup, in-memory, not stored. **Limits are stated plainly and up
   front** (size cap, rate limit): honesty about the limit is part of the
   generosity — a surprise 429 is a betrayal, a documented one is a
   boundary. The limit line and the remove-the-limit line sit together:
   "Free: 25 MB, N requests/min. Need more? [paid tier]."
3. **Paid** — removes the limits and covers what is *expensive* to run:
   GPU OCR, video captioning, frontier transcription, volume. Framing:
   "rent our GPUs or bring your own" — the self-host path stays
   documented next to the buy button, because "you can leave at any time"
   is the trust that makes anyone willing to arrive. (Pricing model
   itself — subscription vs pay-as-you-go — is an open decision: see
   docs/PRICING-NOTES.md.)

Every tier is a continuation of the generosity of the one before it, never
the end of it.

## 6. Visual identity (summary — full system in docs/DESIGN.md)

- **The product's output is the imagery.** Terminal/notebook blocks are
  the hero, and they are dark — but the *pages around them* must work in
  light too, because the primary audience lives in notebooks (Jupyter,
  RStudio, Quarto), which default light. Docs ship a real light mode.
- **Wordmark:** lowercase `attachments` set in the monospace stack. No
  mascot, no paperclip (Clippy adjacency is fatal in this market).
- **Mark (favicon/avatar):** the DSL brackets — `[a]` — our own syntax as
  the icon. Works at 16 px, monochrome-safe.
- **Color:** terminal green `#7ee787` (accent / success / prompts) and
  terminal blue `#79c0ff` (links / keywords) on near-black `#0f1115`.
  Amber `#f0b72f` for notes/hints only — never for marketing emphasis.
- **Type:** one monospace stack for code, wordmark, and anything the
  product "says"; one system sans for prose. Nothing else.
- **The terminal block is the hero unit.** Marketing pages lead with a
  rendered REPL session, not an illustration. The product's own output is
  the imagery.

## 7. Quick test

Before shipping any user-facing words, ask:

1. Would a precise senior engineer say this, unprompted, to a colleague?
2. Does every failure path leave the reader with a concrete next step?
3. Is the local path mentioned before the hosted one?
4. Did we claim an adjective instead of showing the behavior?
5. Is there an exclamation point? Remove it.
