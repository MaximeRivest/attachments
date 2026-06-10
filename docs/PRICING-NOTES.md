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
| **Batch** GPU OCR (LightOnOCR) — results in minutes, not seconds | **$0.0025 / page** | 4,000 pages |
| **Live** GPU OCR — synchronous, when a warm GPU exists | **$0.005 / page** | 2,000 pages |
| Transcription | **$0.0067 / audio minute** (= $1 per 150 min) | 1,500 minutes (25 h) |
| Light formats (pdf-with-text, xlsx, docx, …) | not metered | — |

Concretely: 1,000 invoices = $2.50 batched, back in ~25–30 minutes
(≈17 min GPU at ~1 page/s + ~5 min cold start).

Rules:
- Published numbers are a **floor, not an estimate** — when actuals are
  rounded, they round in the user's favor. Metered billing is where
  users expect to be nickeled; being visibly rounded-toward-them is
  cheap and buys disproportionate trust.
- Light formats stay unmetered on paid keys: metering pennies for a CSV
  would cost more goodwill than it earns. The paid tier exists for what
  is expensive to run (GPU, volume), per BRAND §5.
- The 50% batch discount matches industry convention (Mistral, OpenAI
  batch APIs), so it reads as normal, not as a downgrade.

### Market position (verified 2026-06)

| Provider | $/1,000 pages |
|---|---|
| Textract / Azure Read / Google Doc AI (raw OCR) | $1.50 |
| LlamaParse fast | $1.25 |
| Mistral OCR | $2.00 (~$1.00 batch) |
| **us — batch** | **$2.50** |
| Datalab Marker | $4.00 |
| **us — live** | **$5.00** |
| Unstructured hi-res | $10.00 |
| Reducto | $15.00+ |

Mid-market: ~3× hyperscaler raw OCR, under the quality-parsing tier
(Datalab/Unstructured/Reducto) — right neighborhood, because the product
is the context layer, not raw OCR. Transcription at $0.0067/min is at
market (OpenAI $0.006, Deepgram $0.0043, AssemblyAI ~$0.0025).

## GPU strategy: batch-first

The margin killer is GPU **idleness**, not the metered rate. At ~1
page/s (conservative L4 estimate; LightOn publishes 5.71 pages/s on an
H100, no L4 numbers), compute costs $0.12–0.25 per 1,000 pages — a
95–97% gross margin *while busy*. Idle, an on-demand g6.xlarge burns
~$653/mo (ca-central; spot ~$321/mo).

So:
1. **Launch batch-only.** Paid OCR jobs queue; when the queue is
   non-empty an autoscaler starts a spot g6.xlarge, vLLM loads the 1B
   model (~3–5 min cold start), drains the queue at ~full utilization,
   terminates after a few idle minutes. We never pay for an idle GPU.
2. **Go warm when demand justifies it.** Break-even-within-$50/mo needs
   roughly: 4,000 pages/day (on-demand box, live price) or ~1,800–3,600
   pages/day (spot, live/batch price). Equivalently ~21 subscriptions
   cover the on-demand box outright. Past that point the GPU is ~1.5%
   utilized at break-even — every additional page is nearly pure margin.
3. **Playground quality preview**: LightOnOCR is 1B params, Apache 2.0 —
   it can run on CPU (vLLM CPU backend), likely 30–120 s/page on the
   current m6i.large (unbenchmarked). Plausibly fine for a single-page
   "taste the quality" demo with an honest "this takes about a minute"
   label. Cheaper-than-warm-GPU options to evaluate: serverless GPU
   (Modal/RunPod/Replicate — per-second billing, zero idle, seconds-level
   cold starts) or an always-on g4dn.xlarge T4 spot (~$120–190/mo).

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

- **Benchmark LightOnOCR-2-1B on an L4 (g6.xlarge) — gates final
  prices.** All published numbers are H100-only. Blocked on an AWS GPU
  quota increase (requested 2026-06-10). Also benchmark the vLLM CPU
  backend for the playground preview idea.
- **First real datapoint (2026-06-10, home 3090, severely constrained):**
  0.33 pages/s (3.07 s/page, ~816 output tokens/page, output quality
  good) with vLLM squeezed into the 3.4 GB left over beside other
  services — KV cache of only 5.3k tokens meant batching couldn't help
  (concurrency 4/8/16 all ~0.32 pages/s, flat = cache-starved, not
  GPU-bound). Treat as a hard floor: even this floor is ~28k pages/day
  ≈ 855k pages/month per GPU. A clean 3090 run (model + real KV cache)
  should batch 3–10× higher; measure before setting final prices.
- Batch turnaround promise: "minutes, not seconds" needs a number we can
  defend (queue SLA, e.g. "typically under 30 minutes") once the
  autoscaler exists.
- Serverless GPU (Modal/RunPod/Replicate) vs own spot autoscaler for
  batch + playground — cost and complexity comparison.
- Final per-unit prices (table above is the working proposal; $5/1k live
  is on the confident side of mid-market — $3–4/1k would undercut
  Datalab while keeping ~95% busy-margin).
- Whether the subscription's included quota rolls over (lean: no, but
  unused *pack* credits always keep working — that's the no-expiry
  promise).
- Institutional invoicing (POs) — defer until someone asks twice.
