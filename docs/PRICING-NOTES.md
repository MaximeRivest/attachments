# Pricing — open decisions

> Status: **undecided.** This file scopes the decision so an agent (or
> human) can work it. Constraints come from docs/BRAND.md (§4, §5) and are
> not up for renegotiation; the pricing *model* is.

## What is already decided (brand law)

- **Free hosted tier exists** and covers what is annoying to install
  (OCR, transcription, dependency-hell formats). No key, no signup,
  in-memory, not stored.
- **The free tier is rate-limited, and the limit is stated plainly and up
  front.** A documented limit is a boundary; a surprise 429 is a betrayal.
  The limit line and the remove-the-limit line always sit together:
  "Free: 25 MB, N requests/min. Need more? [paid tier]."
- **Paying removes the limits** and covers what is expensive to run (GPU
  OCR, video captioning, frontier transcription, volume).
- Self-host stays documented next to the buy button. Never salesy: no
  urgency, no "unlock," capability + cost in a table, sober voice.

## The decision to make: subscription vs pay-as-you-go (vs hybrid)

The audience (BRAND.md §1b) is scientists, R/Julia/Python data people,
grad students — not infra engineers with a procurement card. Implications
to weigh:

**Pay-as-you-go**
- Pro: matches bursty, project-shaped usage (a thesis chapter, one batch
  of scans, a field season of recordings). No guilt of an idle
  subscription — this crowd cancels subscriptions they don't use weekly.
- Pro: "honest numbers" brand trait maps naturally to per-unit prices
  (per page OCR'd, per audio minute).
- Con: requires metering, prepaid credits or cards on file; surprise
  bills are the salesy-adjacent failure mode. Caps/alerts would be
  mandatory.

**Subscription**
- Pro: predictable for us and for a lab paying from a grant line (grants
  like fixed costs; many institutions can't do variable billing).
- Pro: simplest to explain: "free with limits / $X removes them."
- Con: bad fit for someone who needs OCR for one week in March; an
  unused subscription erodes the give-first trust.

**Hybrid (likely worth modeling first)**
- Free tier → prepaid credit packs (no card on file, no expiry pressure)
  → flat subscription for sustained/volume users and labs. Credits handle
  the bursty scientist; the subscription handles the lab and the app
  developer (secondary audience).

## Questions the worker should answer

1. What are the free tier's actual numbers (size cap, requests/min,
   requests/day)? They must be cheap enough to be genuinely generous and
   real enough to bound abuse. Pick numbers, cost them out.
2. Unit of metering for paid: request? page? audio minute? token?
   (Honesty rule: the unit must be something the user can predict before
   sending the file.)
3. Do credits expire? (Brand lean: no, or very long — expiring credits
   read as a catch.)
4. Lab/team story: one shared key with a pooled limit? Invoicing for
   institutions?
5. Where does the price live on the site? (DESIGN.md §9: never address
   the visitor as a buyer; a capability + cost table, no "plans" page
   theatrics.)
6. Rate-limit UX: what does the 429 body say? It is an error that
   teaches — state the limit, when it resets, and both remedies (wait /
   paid), local-first ordering does not apply here but sober tone does.

## Deliverable

A short proposal (one page) recommending a model, the free-tier numbers,
and the paid unit prices, checked against BRAND.md §7's quick test.
