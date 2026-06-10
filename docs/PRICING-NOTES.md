# Pricing — decisions

> Status: **decided 2026-06-10** (model, units, free tier, anchors).
> Per-unit prices below are proposed and editable until the paid tier
> ships. Brand constraints come from docs/BRAND.md (§4, §5) and are not
> up for renegotiation. Implementation plan: attachments-web/PLAN.md
> (phase 3 — auth + Stripe).

## The model: hybrid

1. **Free hosted tier** — keyless, no signup, unchanged.
2. **Credit packs** — prepaid, via Stripe Checkout. **Credits never
   expire.** No card on file. For the bursty user: a thesis chapter, one
   batch of scans, a field season of recordings.
3. **Subscription** — flat monthly, for labs and apps: predictable for a
   grant line item, pooled key for a team.

Each tier is a continuation of the generosity of the one before it.
Paying removes limits; it never gates what was free.

## Free tier (published numbers, already live except the daily cap)

| Limit | Value | Why |
|---|---|---|
| File size | 25 MB | nginx + server cap, live today |
| Rate | 10 requests/min per IP | live today |
| Daily cap | 200 requests/day per IP | **to add** — bounds the worst-case cost of one scripted user (10/min alone allows 14,400/day). Invisible to humans, decisive against scrapers. |
| Storage | none — processed in memory | live today |

The 429 body must say which limit was hit and when it resets (an error
that teaches; sober tone, both remedies: wait, or the paid tier).

## Metering units and prices (proposed — refine before launch)

Brand rule: the user must be able to predict cost before sending the
file. So we meter what they can count: pages and minutes.

| What | Price | $10 buys |
|---|---|---|
| GPU OCR (LightOnOCR) | **$0.005 / page** | 2,000 pages |
| Transcription | **$0.0067 / audio minute** (= $1 per 150 min) | 1,500 minutes (25 h) |
| Light formats (pdf-with-text, xlsx, docx, …) | not metered | — |

Rules:
- Published numbers are a **floor, not an estimate** — when actuals are
  rounded, they round in the user's favor. Metered billing is where
  users expect to be nickeled; being visibly rounded-toward-them is
  cheap and buys disproportionate trust.
- Light formats stay unmetered on paid keys: metering pennies for a CSV
  would cost more goodwill than it earns. The paid tier exists for what
  is expensive to run (GPU, volume), per BRAND §5.
- Cost sanity: CPU OCR costs us ~$0.0002–0.001/page on the current
  m6i.large; GPU pricing must amortize a g6.xlarge (~$590/mo on-demand —
  run spot/on-demand until subscriber count covers always-on).

## Anchors

| Offer | Price | Contents |
|---|---|---|
| Credit pack (entry) | **$10** | impulse-purchasable for a grad student; no approval conversation |
| Subscription | **$29 / month** | no rate limit, 100 MB files, pooled team key, 10,000 OCR pages + 5,000 transcription minutes included monthly, then pack rates |
| (Later, only if pulled) | $99 / month | team/volume tier — room left above $29 so nobody ever gets repriced |

~20 subscribers cover an always-on GPU box; until then GPU runs
on-demand. Starting slightly conservative and adding generosity later is
recoverable; starting too cheap is not — repricing erodes exactly the
trust the brand runs on.

## Implementation notes (for the auth/billing phase)

- Stripe Checkout + customer portal only; we never touch card data.
  Packs = one-time payments crediting a quota table; subscription =
  Stripe Billing; webhook updates the key's quota.
- Auth: email magic-link or GitHub OAuth → API key. The keyless free
  tier is untouched.
- Usage visibility: one dashboard page — key, usage this month,
  remaining credits, invoices link. No "plans" theatrics (DESIGN.md §9).
- Self-host stays documented next to the buy button: "rent our GPUs or
  bring your own."

## Still open

- Final per-unit prices (table above is the working proposal; validate
  against real GPU throughput once LightOnOCR is benchmarked).
- Whether the subscription's included quota rolls over (lean: no, but
  unused *pack* credits always keep working — that's the no-expiry
  promise).
- Institutional invoicing (POs) — defer until someone asks twice.
