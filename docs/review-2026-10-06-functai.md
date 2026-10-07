# Review before 1.0: Attachments as FunctAI's file input (2026-10-06)

Reviewed: this repository at `b582977` (1.0.0a1), with lmcc 0.8.5 and
functai 1.2.0. All 999 tests pass (7 min, all extras). The FunctAI side of
the plan is `functai/design/13-files-and-attachments.md`. The bridge lives
in FunctAI: nothing here should import lmcc or FunctAI.

## What is right, and should not change

- **The Artifact IR** (`{text, images, audio, video, meta}`), frozen, with a
  JSON Schema, conformance tests, typed error codes and page/sheet/slide
  segments. This is exactly the neutral value FunctAI needs: it can be the
  input's shape in all four FunctAI languages.
- **Deterministic output.** The same PDF processed twice gives identical
  bytes, images included, so cache keys built on it are stable.
- **Zero required dependencies**, magic-byte routing, the DSL with
  discoverable options, "did you mean" warnings, errors as data.

## Release blockers (independent of FunctAI)

1. **`service_url` defaults to `https://api.attachments.dev/v1`**, and
   `attachments.dev` does not resolve today. LAUNCH.md §7 already says: buy
   and park the domain, or default to `None`. Whoever registers it later
   would receive users' files and keys.
2. **Stale empty folders in `src/attachments/`** (`data`, `loaders`,
   `onefile_pipelines`, `pipelines`, `presenters`: only `__pycache__`,
   untracked) end up as 12 empty directory entries in the wheel built from
   this checkout. Delete them, or build from a clean clone.
3. **Untracked files** (`.claude/`, `docs/examples/`,
   `docs/_generated_dsl_cheatsheet.md`): commit or ignore before tagging.
4. `attachmentsv3` is fully contained in this repository (its last commit
   `0c444cc` is here): it can be archived.

## Needed for FunctAI (and good for every other consumer)

Ordered by importance. Each is small, public and provider-neutral.

1. **The wire form as public API, both ways.** `Artifacts.to_json()` (images
   as `bytes_b64`, exactly the schema in `spec/artifact.schema.json`) and
   `Artifacts.from_json(data)`. Today only `server.py` (privately) and
   `service.py` (decoding) do it. FunctAI must write every input as JSON
   (its log, cache key, replay, saved programs), and rebuild it on replay.
   Keep the method names plain; do not imitate pydantic.
2. **`Artifacts.parts(*, sources=False, interleave=True)`**: the
   provider-neutral content list the `claude()` and `openai()` presenters are
   built from: `{"type": "text", "text"}` and `{"type": "image",
   "media_type", "data"}` (base64), the shape lm15 parts take. With
   `interleave`, a page's text is followed by that page's image (from
   `segments` and `ImageItem.page`); today every presenter puts all text
   first and every image after, so the model must match page 7's picture to
   page 7's words by itself. FunctAI's bridge then only maps parts to lm15.
3. **Errors that can raise.** `att()` never raises: a missing file is one
   artifact with `meta.error` and empty text, which a program that forgets to
   check sends as an empty document (the model answers anyway). Add
   `att(..., errors="raise")` (or `Artifacts.raise_for_errors()`); FunctAI
   will refuse error artifacts either way.
4. **File names are shown to the model.** `.text` starts each file with
   `## <name>`, and an image-only file reads `[image: tabby_cat.png]`. Useful
   for a folder of documents, a label leak for classification, and part of
   every cache key. `render_text` already has `include_sources`; expose it on
   `.text`, the presenters and `parts()`.
5. **Size control for rendered pages.** PDF pages are PNG at 200 dpi: a
   2-page sample made 880 KB (one page 750 KB). Images have `max_dim`, PDFs
   do not. Add `max_dim`, and `format: jpeg` with `quality` for page
   renders. Providers cap image size and count, and every byte is logged
   and cached by FunctAI.
6. **`tokens` ignores images.** 2 pages with 2 page images estimate as 295
   tokens; the images alone cost far more. Count images (even roughly, per
   image or by pixels) or say so in the summary line.
7. **Keep the original bytes, optionally** (later, not 1.0): providers read
   PDFs natively (lm15 `DocumentPart`), sometimes cheaper and better than
   text + page images. An opt-in `meta.extra` or a reserved key would let a
   consumer choose. Needs an IR decision, so after 1.0.

## Not Attachments' job (for the record)

Media by reference in logs, refusing error artifacts, choosing what the
model sees, and the four-language story are FunctAI's (design note 13).
Mapping lm15's own `ImagePart` to a media input is lmcc's.
