# Presenting artifacts (v1)

How a list of artifacts becomes what a model reads, and the rules around
it that every implementation shares. Text, offsets, white space and
rounding follow [README.md](README.md#text-numbers-and-white-space). The
cases in `cases/` are the examples; this page is the rule.

Everything here is pure: no file, no network, no clock. Each function
takes artifacts in process (`bytes`) or in wire form (`bytes_b64`).

## Names shown or hidden: `sources`

Every presenter takes `sources` (default true): whether file names reach
the output.

- **Shown artifacts.** With `sources` false, artifacts whose `meta.kind`
  is `"directory"` (folder overviews, made of names) are left out
  entirely.
- **Header.** An artifact's header is `## ` + `meta.source`, or
  `## (unknown)` when it has none (or it is empty).
- **Named labels.** With `sources` false, presenting parts gives a
  warning (kind `named-labels`) when a shown artifact with images has
  `meta.extra.watermark` containing `{name}`: the name is drawn on its
  pictures and cannot be hidden.

## Text

For each shown artifact, in order:

1. its text, stripped; if empty and it has images, one line per image:
   `[image: <name>]` (name `image` when it has none) with `sources`,
   `[image]` without; if empty with no images, the artifact is skipped;
2. with `sources`, the header line first.

Blocks are joined by one blank line (`"\n\n"`). No artifacts: `""`.

## Image data

An image's data is its `bytes` encoded as standard base64 (with padding),
else its `bytes_b64` when that is a non-empty string, else it has no
data: presenters skip it. Its media type is `mimetype`, else
`application/octet-stream`.

## Parts

Two shapes: `{"type": "text", "text"}` and
`{"type": "image", "media_type", "data"}` (base64).

**Interleaved** (`interleave` true, the default). For each shown
artifact:

1. *Pieces.* The artifact's *paged segments* are its `meta.segments` whose
   `page`, `start` and `end` are all integers, sorted by
   `(start, end, page)`. Images with data are kept with their `page`
   (an integer, else none). If there is at least one paged segment and
   at least one image with a page: walk the segments in order, keeping a
   cursor into the text (starting at 0) and the images not yet placed;
   for each segment:
   - images whose page is less than the segment's page are placed: first
     the text from the cursor to the segment's `start` is emitted, then
     those images (in their original order);
   - images whose page equals the segment's page are placed: first the
     text from the cursor to the segment's `end`, then those images.

   Emitting text from the cursor to `n` does nothing when `n` is not past
   the cursor; otherwise the slice, stripped, becomes a text piece if it
   is not empty, and the cursor moves to `n`. After the walk (or without
   one), the rest of the text is emitted, then every image not placed, in
   original order.
2. *Header.* If the artifact gave no pieces it is skipped. With
   `sources`, the header goes before the first piece: joined to it by a
   line feed when it is text, else as a text piece of its own.
3. *Merging.* Each piece is appended to the result; a text piece that
   follows a text piece is merged into it, separated by a blank line.
   This merging crosses artifacts (two text-only artifacts give one part)
   but never crosses an image.

**Not interleaved.** One text part with the whole Text (if it is not
empty), then every image with data of every shown artifact, in order.

**Prompt.** A non-empty `prompt` is appended last as its own text part,
never merged.

## Claude, OpenAI, lm15

Each is one user message built from the parts, with the same arguments:

- Claude: `[{"role": "user", "content": blocks}]`; a text part is
  `{"type": "text", "text"}`, an image part
  `{"type": "image", "source": {"type": "base64", "media_type", "data"}}`.
- OpenAI Chat Completions: `[{"role": "user", "content": parts}]`; an
  image part is `{"type": "image_url", "image_url": {"url":
  "data:<media_type>;base64,<data>"}}`.
- lm15: one `Message` with role `user` and lm15 text and image parts
  (inline base64), in lm15's own types for the language. No parts at
  all (nothing to show and no prompt) is refused.

Claude's and OpenAI's messages are checked against their published
limits (below); a problem gives a warning of kind `request-limit` and
the messages are still returned.

## Request limits

Measured on the parts. *Picture bytes*: the sum of the lengths of the
images' base64 data. *Request size*: picture bytes + the JSON size of
each text part's text + 100 per part + 200. A picture's *size* in pixels
is read from its first 87,384 base64 characters, else from all of it
(see Image sizes); pictures whose size cannot be read are not counted.

| | Claude | OpenAI |
|---|---|---|
| request | 32,000,000 bytes (Bedrock: 20 MB, Google Cloud: 30 MB) | 512,000,000 |
| pictures | 100 (100 for models with a 200k-token context, 600 for others) | 1,500 |
| one picture | 10,000,000 base64 bytes (5 MB on Bedrock and Google Cloud) | — |
| sides | 8,000 px; 2,000 px when there are more than 20 pictures | — |
| types | gif, jpeg, png, webp | gif, jpeg, png, webp |

The problems, one sentence each and word for word as in the `limits`
cases, in this order: request size, picture count, pictures too big
(`a picture is` / `N pictures are up to`), types (sorted, then the
accepted ones by subtype), sides. Then one `Fix:` line joining with `; `:

- a size problem (request bytes, picture bytes, sides) with pictures:
  `image_format: jpeg (…)` when PNG data is more than half the picture
  bytes, then `max_dim: 1568 (…)`;
- too many pictures, or a size problem with more than one picture:
  `fewer pages per request, e.g. pages: 1-N` (N = half of the smaller of
  the picture count and the limit, at least 1; `pages: 1` when N is 1);
  else a size problem with no pictures: `fewer files or pages per request`;
- a type problem: `image_format: png (converts the picture)`.

The warning's text is `This <provider> request would be rejected:`
followed by each problem as `  - <problem>` and the fix as `  Fix: …`.

## Chunks

`chunk(max_chars, max_tokens, overlap = 200, sources)`. The cap is the
smaller of `max_chars` and `max_tokens × 4` when given, else 8,000; a cap
below 1 is refused. `overlap` is clamped to `[0, cap − 1]`.

For each shown artifact whose text is not only white space:

- **With segments**: each segment's `(start, end)` is clamped to the
  text (`start` to `[0, n]`, `end` to `[start, n]`); empty spans are
  dropped; spans are sorted. Then, from the first span: a span longer
  than the cap is cut into windows (below) of its own text; otherwise
  following spans are added while `max(end, next end) − start` fits the
  cap, and the text from `start` to the furthest `end` is one chunk.
- **Without**: the whole text is cut into windows.

**Windows** of a text of length n: if n ≤ cap, the text itself (nothing
if empty). Otherwise, from `start` = 0: `end` = min(start + cap, n); if
`end` < n, look for the last `"\n\n"`, else `"\n"`, else `" "` that lies
entirely within `[max(start, end − max(1, cap ÷ 5)), end)` (integer
division); if found, and the position just after it is past `start`,
`end` becomes that position. The window is `[start, end)`. Stop when
`end` reaches n; else `start` = max(end − overlap, start + 1).

With `sources` each chunk is the header, a line feed, then the chunk.

## Token estimates

`estimate_tokens(tier = "high")` → `{"text", "images", "total"}`. Text:
the code points of every artifact's text (all artifacts, overviews
included), divided by 4, rounded up. Images: for each image of every
artifact, its data decoded; no data or invalid base64: 0; a size that
cannot be read: the tier's budget (the most a picture can cost); else
the picture tokens below. Tiers: `high` (edge 2,576 px, budget 4,784)
and `standard` (1,568, 1,568); any other tier is refused.

**Picture tokens** for width × height: 0 if either is ≤ 0. Patches of
w × h: ⌈w/28⌉ × ⌈h/28⌉. A size *fits* when ⌈w/28⌉×28 ≤ edge, ⌈h/28⌉×28 ≤
edge and its patches ≤ budget. A size that fits is kept. Otherwise, for
height > width, solve with the sides swapped and swap back; else with
aspect = width / height (floating point), find by bisection the largest
w in [1, width) such that (w, max(round(w / aspect), 1)) fits: `lo` = 1,
`hi` = width, while `lo + 1 < hi`: `mid` = ⌊(lo+hi)/2⌋, set `lo` = mid if
it fits else `hi` = mid. The size is (lo, max(round(lo / aspect), 1)),
`round` half to even. The tokens are its patches.

## Image sizes

`(width, height)` from a picture's first bytes, or none. Never fails.

- PNG (`89 50 4E 47 0D 0A 1A 0A`): with at least 24 bytes and `IHDR` at
  12–16, two big-endian 32-bit integers at 16 and 20.
- JPEG (`FF D8 FF`): from offset 2, while 4 bytes remain: the byte must
  be `FF` (else none); marker `FF` is a fill byte (advance 1); markers
  `D8`, `01`, `D0`–`D7` have no length (advance 2); otherwise read the
  big-endian length; a start-of-frame marker (`C0`–`CF` except `C4`,
  `C8`, `CC`) gives height then width as big-endian 16-bit integers at
  offset +5 (none if fewer than 9 bytes remain); `D9` or `DA` give none;
  else advance 2 + length.
- GIF (`GIF87a`, `GIF89a`): with at least 10 bytes, little-endian 16-bit
  width and height at 6.
- WebP (`RIFF` at 0, `WEBP` at 8): with at least 30 bytes, by the chunk at
  12: `VP8 `: little-endian 16-bit at 26 and 28, each masked with 0x3FFF;
  `VP8L`: from bytes 21–24, width = 1 + (((b1 & 0x3F) << 8) | b0),
  height = 1 + (((b3 & 0x0F) << 10) | (b2 << 2) | ((b1 & 0xC0) >> 6));
  `VP8X`: 1 + little-endian 24-bit at 24 and at 27.
- BMP (`BM`): with at least 26 bytes, the little-endian 32-bit header
  size at 14; 12 (OS/2): 16-bit width and height at 18; else signed
  32-bit at 18 and 22, absolute values.
- Anything else, too short, or a width or height ≤ 0: none.

## The printed summary

The one-line summary (Python's `repr`, TypeScript's `inspect`):
`<Artifacts: ` + the summary + `>`, then error, warning and note lines.

Summary, joined by ` | `: `N artifact(s)` (singular only for 1);
`C chars` (code points of all texts, thousands with commas); `~T tokens`
(the estimate's total, compact) plus ` (images ~I)` when the images'
share is not 0; `N image(s)` when there are any; `N error(s)` when any.
Compact: under 1,000 as is; else divided by 1,000 (`k`) or by 1,000,000
from a million (`M`), one decimal, a trailing `.0` dropped.

Lines, each list capped at 10 (then `  … +N more error(s) (see .errors)`,
`  … +N more warning(s)`, `  … +N more note(s)`):

- errors: `  ! ` + `source: code — message`;
- warnings (`meta.warnings` of every artifact): `  ! source: warning`;
- notes (`meta.note`): `  * source: note`.

Messages longer than 160 code points are cut in the middle: the first 79,
`…`, the last 80. Lines with the same content (after cutting) collapse
into one, first seen first: `content (xN)` without the source. An error's
source is `meta.source`, or `(unknown)`.

**The error listing failures** (`raise_for_errors`, `throwIfErrors`):
one failure: `source: code — message`; several:
`N inputs failed:` then one line per failure, indented two spaces.

## Options and page selections

**Resolving** raw options (from the syntax and from the call, the call's
last) against a format's declared options (`dsl-schema.json`): each key
is looked up among names, then aliases, then `param` names (a hidden
alias), the first declaration winning. A later key that resolves to the
same option replaces an earlier one.

- Unknown keys are dropped with a warning; the suggestion is the closest
  spelling among names and aliases by Python's `difflib.get_close_matches`
  (Ratcliff/Obershelp ratio, cutoff 0.6, the best score, a tie going to
  the spelling that sorts last), always named by the option it belongs to.
- Values are coerced by the option's type; a value that does not fit is
  dropped with a warning:
  - `str`: a boolean as `true`/`false`, a range as `N-M`, other values as
    their text;
  - `int`: an integer, or text of an optional `-` and digits (not a
    boolean, not a fraction);
  - `bool`: a boolean, or `true yes on false no off` in any case;
  - `bool_or_auto`: as `bool`, or `auto`/`always` in any case (lowercased);
  - `str_or_int`: text or an integer, kept as is;
  - `pages`: a page selection (below).

**Page selections.** A value is an integer, a range (two integers), or
text of comma-separated items; empty items are skipped; none left is
refused. An item, white space trimmed, is `A`, `A-B` or `A-` with `A`, `B`
optionally negative integers (white space allowed around the `-`). `0`
anywhere is refused; positive `A > B` is refused. Negative numbers count
from the end (`-1` is the last page). A selection picks, for a document
of n pages, every page in any item's range (an open end is n; numbers
past the document are ignored), each once, in document order. Its text
is its items joined by `,`: `A` when both ends are equal, `A-` when
open, else `A-B`.
