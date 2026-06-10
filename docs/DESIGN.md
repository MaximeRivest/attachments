# attachments — design system

> Implements docs/BRAND.md visually. This is the source of truth for the
> website, docs theme, social cards, README badges, and any future UI
> (dashboard). If a pixel decision is not covered here, derive it from the
> brand traits: precise, generous, honest — never salesy.

---

## 1. Design concept

**The product's own output is the imagery.** attachments is a tool whose
entire user experience is text in a code block — most often a notebook
cell (Jupyter, RStudio/Positron, Quarto, Colab), sometimes a terminal.
The design system treats that code block as the canonical canvas and a
real session as the hero illustration. Blocks render the way the
audience's environment renders them: light, quiet, a notebook cell —
not a dark terminal (see BRAND.md §1b). No stock art, no abstract
gradients, no 3D blobs, no screenshots-of-screenshots. If a page needs a
visual, it shows the product *running*.

Reference points (and why):
- **Stripe docs** — code samples as the visual hero; we go further: the
  *output* is the hero, not just the input.
- **uv / ruff (Astral)** — proof that a dev tool can feel premium with
  one accent color and disciplined typography.
- **man pages / TUI aesthetics** — density and alignment as beauty.

Anti-references: generic SaaS landing pages (purple gradient, floating
cards, "Trusted by" logo soup), AI-product glow effects.

## 2. Color

**Light-first.** The audience reads in Jupyter, RStudio, Colab, and Quarto
— light by default. The page should feel like their environment: a clean
notebook, a well-set paper. Near-monochrome: ink on paper, **one** accent.

> History note: the first palette (`#7ee787` green / `#79c0ff` blue on
> `#0f1115`) was GitHub's dark syntax theme, inherited from the first
> site draft and canonized after the fact. It encoded a terminal-first
> bias the brand explicitly rejects (BRAND.md §1b). Replaced 2026-06.

### Core palette (light, default)

| Token | Hex | Role |
|---|---|---|
| `--bg` | `#fcfcfb` | Page background (warm paper, not pure white) |
| `--panel` | `#f6f6f4` | Code/notebook blocks, cards |
| `--border` | `#e4e5e2` | 1px borders, dividers |
| `--text` | `#21262c` | Body text (ink, not pure black) |
| `--dim` | `#6b7280` | Secondary text, comments, prompts, captions |
| `--accent` | `#0f766e` | Viridis teal: success, strings, the word "free" — the only chromatic accent in prose. Chosen because viridis is the colormap of scientific plotting (matplotlib, ggplot2, Julia) — the audience's own color — and because GitHub-green (`#1a7f37`) is every dev tool's accent; teal-on-paper is ownable. |
| `--warn` | `#9a6700` | Amber: `*` note/hint lines, inside output blocks only |
| `--error` | `#cf222e` | Red: `!` error lines, inside output blocks only |

There is no second accent. Links are underlined ink (`--text` with a
`--dim` underline at rest), the register of an academic paper — which is
who is reading. Keywords in code are plain ink at weight 600, not blue.

### Dark variant (courtesy, via `prefers-color-scheme`)

bg `#0f1115`, panel `#161a21`, border `#262c37`, text `#d7dde6`,
dim `#8b94a3`, accent `#36c2ae` (viridis teal, lightened for dark bg),
warn `#f0b72f`, error `#ff7b72`.
Same single-accent discipline; dark is an adaptation, never the source
of truth.

### Usage rules

1. **Green is earned.** `--accent` marks success, working examples,
   strings in real runs, and the word "free." Never decorative emphasis,
   never a CTA asking for something.
2. **Amber and red are semantic only**, mirroring the repr's `*` and `!`
   lines, and appear only inside code/output blocks.
3. **One accent, period.** If a design wants a second color, the design
   is wrong. Hierarchy comes from weight, size, and space.
4. **No gradients.** Anywhere.

## 3. Typography

Two stacks, no webfonts (zero-dependency is a brand value; system fonts
load instantly and render natively everywhere):

```css
--mono:  ui-monospace, 'SF Mono', 'Cascadia Code', Menlo, Consolas, monospace;
--serif: Charter, 'Bitstream Charter', Cambria, Georgia, serif;
--sans:  system-ui, -apple-system, 'Segoe UI', sans-serif;
```

Three voices, each with a job — this is a decision, not a fallback stack:

- **Mono** is the product speaking: reprs, errors, hints, options, file
  names, code, the wordmark.
- **Serif** is prose *about* the product: body text, explanations. The
  register of a well-set paper — what the audience reads all day — and
  instantly differentiated from every sans-serif SaaS page. Charter ships
  with macOS; Cambria with Windows; Georgia is the universal fallback.
  All designed for screens.
- **Sans** is UI chrome only: nav, buttons, pills, table headers,
  captions. Never body prose.

| Element | Stack | Size / weight |
|---|---|---|
| Wordmark, h1 | mono | 2rem / 650, letter-spacing -0.02em |
| Section headings (h2) | sans | 1.3rem / 600 |
| Body prose | serif | 1.05rem / 400, line-height 1.65 |
| Code blocks | mono | 0.86rem, line-height 1.55 |
| Pills / inline code | mono | 0.85rem |
| Nav, captions, footers | sans | 0.88–0.9rem, `--dim` |

Rules:
- **Anything the product "says" is monospace.** Prose about the product
  is serif; UI chrome is sans. This three-voice boundary is the visual
  grammar of the whole system.
- Max line length for prose: ~70ch (the 880px container does this).
- No font weights above 650. No italics in terminal blocks.

## 4. The wordmark and mark

- **Wordmark:** `attachments` lowercase, mono stack, weight 650, in
  `--text` (ink on light, light on dark). Single-color always; never
  gradient, never two-tone.
- **Mark:** `[a]` — the DSL brackets around lowercase a, mono. Use for
  favicon, avatars, social profile. At 16px render as text, not paths.
  Brackets in `--dim` or `--border`-weight stroke; the `a` in `--text`
  (or `--accent` on marketing avatars).
- **Clear space:** half the cap-height on all sides.
- **Never:** a paperclip, a clip icon, any skeuomorph of "attachment."
  The email-attachment metaphor is legacy naming, not identity.

## 5. The code block (hero component)

The signature component. Specification:

```css
.term {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  font-family: var(--mono);
  font-size: 0.86rem;
  line-height: 1.55;
  padding: 18px 20px;
  overflow-x: auto;
  white-space: pre;
}
```

Syntax classes (match the repr semantics exactly):

| Class | Color | Used for |
|---|---|---|
| `.p` | `--dim` | Prompts: `$`, `>>>` |
| `.g` | `--accent` | Strings, success values |
| `.b` | `--text`, weight 600 | Keywords: `from`, `import` — ink, not a second color |
| `.y` | `--warn` | `*` note lines |
| `.r` | `--error` | `!` error lines |
| `.c` | `#6e7681` | Comments |

Rules:
1. **Every terminal block must be a real run.** Copy-paste it into a REPL
   and it works, byte for byte. (Same discipline as the README's "real
   runs.") Fabricated output is a brand violation.
2. The repr line `<Artifacts: ...>` appears un-highlighted (plain
   `--text`) — it is the product speaking, not syntax.
3. Blocks never exceed ~14 lines on marketing pages; link to docs for more.
4. No window chrome (traffic-light dots). We are a code block, not a
   macOS ad.
5. **The notebook cell is an equal hero.** `_repr_markdown_` output
   (summaries, admonitions, thumbnails) is the same brand surface as the
   terminal repr; screenshots of a notebook cell are as canonical as a
   REPL session, and often closer to how the audience actually sees the
   product.

## 6. Other components

- **Pills** (`.pill`): format/source chips. Panel bg, 1px border, 6px
  radius, mono 0.85rem. Dim secondary text inside is allowed
  (`.pdf + OCR`). Pills are informational, never clickable-looking unless
  they are links.
- **Cards** (`.card`): panel bg, 1px border, 10px radius, 20px padding.
  For paired concepts (The Artifact / The DSL). Max 2 columns; collapse
  to 1 below 700px.
- **Links:** ink (`--text`) with a `--dim`-colored underline at rest,
  full-ink underline on hover — the register of an academic paper. Never
  buttons-styled-as-links or links-styled-as-buttons on the marketing
  site; the only CTA is a copyable `pip install` line.
- **The install line is the CTA.** `$ pip install attachments` in a
  terminal block with a copy affordance. No "Get Started Free →" buttons.

## 7. Layout

- Single column, `max-width: 880px`, 24px side padding.
- Section rhythm: 64px between sections, 72px top padding on the hero.
- No sticky headers, no cookie banners (nothing to consent to), no
  scroll-triggered animation. Motion budget: zero, except `:hover`
  transitions ≤150ms.
- Page weight budget for attachments.dev: **< 50 KB total, zero requests
  beyond the HTML** (inline CSS, no JS unless a copy-button demands ~10
  lines). This is the "zero required dependencies" value, expressed as a
  website.

## 8. Imagery and social

- **Social card (og:image):** dark panel, the repr line centered in mono,
  wordmark bottom-left, `[a]` mark bottom-right. Generate once as a
  static PNG (1200x630). No headshots, no gradients.
- **README header:** none, or a single terminal-block screenshot (SVG
  preferred for crispness). Badge row allowed: PyPI version, CI, license —
  default shields style, no custom colors (badges are infrastructure, not
  decoration).
- **Talks/slides:** dark bg, one terminal block per slide, mono headings.

## 9. Writing on the page (interface copy)

Defers to docs/BRAND.md §3. Page-specific additions:

- Headings are statements, not invitations: "What it eats," "You can
  leave at any time," "Built on a one-page contract" — keep this register.
- Never address the visitor as a buyer ("plans," "pricing," "unlock").
  The paid tier, when it exists, is described as capability + cost, in a
  table, in the same sober voice.
- Every claim links to its proof: "open source" → the repo, "a one-page
  contract" → the spec file, "validated in CI" → the conformance suite.

## 10. Do / Don't summary

| Do | Don't |
|---|---|
| Real REPL output as imagery | Stock art, illustrations, glow effects |
| One green, one blue, semantic amber/red | Gradients, brand-color CTAs |
| System fonts, <50 KB pages | Webfonts, JS frameworks for a static page |
| `[a]` mark, lowercase wordmark | Paperclips, mascots, title case |
| The install line as the only CTA | "Sign up," "Get started," urgency |
| Link every claim to its proof | Adjectives without evidence |
