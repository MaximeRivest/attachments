# attachments — design system

> Implements docs/BRAND.md visually. This is the source of truth for the
> website, docs theme, social cards, README badges, and any future UI
> (dashboard). If a pixel decision is not covered here, derive it from the
> brand traits: precise, generous, honest — never salesy.

---

## 1. Design concept

**The product's own output is the imagery.** attachments is a tool whose
entire user experience is text in a terminal; the design system treats the
terminal as the canonical canvas and the REPL session as the hero
illustration. No stock art, no abstract gradients, no 3D blobs, no
screenshots-of-screenshots. If a page needs a visual, it shows the product
*running*.

Reference points (and why):
- **Stripe docs** — code samples as the visual hero; we go further: the
  *output* is the hero, not just the input.
- **uv / ruff (Astral)** — proof that a dev tool can feel premium with
  one accent color and disciplined typography.
- **man pages / TUI aesthetics** — density and alignment as beauty.

Anti-references: generic SaaS landing pages (purple gradient, floating
cards, "Trusted by" logo soup), AI-product glow effects.

## 2. Color

Dark-first. These tokens already exist in `site/index.html`; they are now
canon and named.

### Core palette (dark, default)

| Token | Hex | Role |
|---|---|---|
| `--bg` | `#0f1115` | Page background (near-black, slightly warm) |
| `--panel` | `#161a21` | Terminal blocks, cards |
| `--border` | `#262c37` | 1px borders, dividers |
| `--text` | `#d7dde6` | Body text |
| `--dim` | `#8b94a3` | Secondary text, comments, captions |
| `--accent` | `#7ee787` | Terminal green: success, prompts, the FREE word, strings in code |
| `--accent2` | `#79c0ff` | Terminal blue: links, keywords |
| `--warn` | `#f0b72f` | Amber: notes/hints (`*` lines) only |
| `--error` | `#ff7b72` | Red: error lines (`!` lines) only — NEW token |

### Usage rules

1. **Green is earned.** `--accent` marks success, working examples, and
   the word "free." It is never used for decorative emphasis or CTAs that
   ask for something.
2. **Amber and red are semantic only.** They mirror the repr's `*` (note)
   and `!` (error) lines. Never use them for marketing highlights.
3. **One accent per block.** A terminal block may use the full syntax
   palette; prose sections use at most green OR blue for emphasis, not both.
4. **No gradients.** Anywhere.

### Light variant (docs only, optional)

Derive by inverting lightness, keep hues: bg `#fbfcfd`, panel `#f2f4f7`,
text `#1c2128`, accent `#1a7f37`, accent2 `#0969da`, warn `#9a6700`,
error `#cf222e`. The marketing site does not ship a light mode; docs may.

## 3. Typography

Two stacks, no webfonts (zero-dependency is a brand value; system fonts
load instantly and render natively everywhere):

```css
--mono: ui-monospace, 'SF Mono', 'Cascadia Code', Menlo, Consolas, monospace;
--sans: system-ui, -apple-system, 'Segoe UI', sans-serif;
```

| Element | Stack | Size / weight |
|---|---|---|
| Wordmark, h1 | mono | 2rem / 650, letter-spacing -0.02em |
| Section headings (h2) | sans | 1.3rem / 600 |
| Body prose | sans | 1rem / 400, line-height 1.6 |
| Terminal blocks | mono | 0.86rem, line-height 1.55 |
| Pills / inline code | mono | 0.85rem |
| Captions, footers | sans | 0.88–0.9rem, `--dim` |

Rules:
- **Anything the product "says" is monospace.** Reprs, errors, hints,
  options, file names, the wordmark itself. Prose *about* the product is
  sans. This boundary is the visual grammar of the whole system.
- Max line length for prose: ~70ch (the 880px container does this).
- No font weights above 650. No italics in terminal blocks.

## 4. The wordmark and mark

- **Wordmark:** `attachments` lowercase, mono stack, weight 650. On dark:
  `--text`. Single-color always; never gradient, never two-tone.
- **Mark:** `[a]` — the DSL brackets around lowercase a, mono. Use for
  favicon, avatars, social profile. At 16px render as text, not paths.
  Brackets in `--dim` or `--border`-weight stroke; the `a` in `--text`
  (or `--accent` on marketing avatars).
- **Clear space:** half the cap-height on all sides.
- **Never:** a paperclip, a clip icon, any skeuomorph of "attachment."
  The email-attachment metaphor is legacy naming, not identity.

## 5. The terminal block (hero component)

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
| `.b` | `--accent2` | Keywords: `from`, `import` |
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
4. No window chrome (traffic-light dots). We are a terminal, not a macOS ad.

## 6. Other components

- **Pills** (`.pill`): format/source chips. Panel bg, 1px border, 6px
  radius, mono 0.85rem. Dim secondary text inside is allowed
  (`.pdf + OCR`). Pills are informational, never clickable-looking unless
  they are links.
- **Cards** (`.card`): panel bg, 1px border, 10px radius, 20px padding.
  For paired concepts (The Artifact / The DSL). Max 2 columns; collapse
  to 1 below 700px.
- **Links:** `--accent2`, no underline at rest, underline on hover. Never
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
