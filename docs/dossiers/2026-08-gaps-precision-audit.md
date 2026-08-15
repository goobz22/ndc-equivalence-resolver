# /gaps precision audit — the top 50 checked against independent regimes

Date: 2026-08-14 · Sweep audited: #1 (data vintage 2026-08-12) · Worksheet:
`ndcres gaps --worksheet 50` (ordering pinned to the gap report by test).

## The question

The instrument flags 377 US drug classes as "evidence consistent with a supply
constraint" while absent from FDA's shortage list. Backward validation exists
(the signals fired a median 112 days before FDA's own historical listings —
docs/VALIDATION.md); this audit asks the FORWARD question: of the top 50
flagged classes today, how many are independently listed by at least one other
public shortage regime?

Regimes checked (citation-only; none feeds the pipeline or any verdict —
operator decision, SPEC §17): ASHP (US practitioner-reported), Australia TGA
and Health Product Shortages Canada (mandatory reporting), UK DHSC/NHS supply
notifications. Access date on every citation: 2026-08-14.

## Result

| measure | value |
|---|---|
| top-50 classes with ≥1 citable independent listing (same molecule + form) | **28 of 50 (56%)** |
| distinct molecules across the 50 | 38 |
| molecules with ≥1 citable listing | 16 (42%) |
| molecules with only mismatched-form / stale partials | 5 |
| molecules with clean misses across all four regimes | 17 |

**A lower bound, and framed as one**: a class not found on the other regimes is
UNCONFIRMED, never false — the FDA list's own historical lag is the finding
this project measures, and the other regimes lag and scope differently too.
Two structural reasons the 56% understates:

1. **Foreign checks have no power over US-only products.** Of the 17
   clean-miss molecules, at least 8 (oxiconazole, naftifine, alclometasone,
   desoximetasone, diflorasone, benzonatate, diethylpropion,
   ibuprofen/famotidine) are niche US-market products with little or no
   marketing in AU/CA/UK — absence from those lists is expected regardless of
   US supply state.
2. **ASHP's intake is practitioner reports**, which skew to hospital and
   high-acuity drugs; quiet retail-generic strain (this instrument's specialty)
   under-reaches it.

## Strongest multi-regime corroborations

- **Estradiol transdermal patches (ranks 39–42)** — ASHP bulletin id=1206
  (updated 2026-04-22, 14 twice-weekly products on backorder/allocation) +
  TGA Limited Availability to Dec 2026 with s19A imports + UK SSP079–082
  extended to 2026-10-02 + multiple Canadian mandatory reports. The
  instrument's original anchor case, still firing, still corroborated.
- **Triamcinolone acetonide injectable (rank 8)** — ASHP current (2026-04-21)
  + Canada Kenalog-40 report (2026-04-14).
- **Lactated Ringer's irrigation (rank 31)** — ASHP current + Australia's
  named national IV-fluids shortage (s19A substitution).
- **Temozolomide (ranks 1, 17)** — TGA Limited Availability through
  2026-09-30 on the matching 140 mg strength; an oncology drug the FDA list
  does not carry.

## Recorded honestly: what did NOT corroborate

Clean misses (all four regimes, same-form): indomethacin ER, paroxetine 40 mg,
benzonatate, nebivolol, desogestrel/EE and norethindrone/EE oral
contraceptives, oxiconazole, alclometasone, naftifine,
erythromycin/benzoyl-peroxide gel (explicitly called a distribution — not
supply — issue by trade press), diethylpropion, diclofenac oral,
ibuprofen/famotidine, desoximetasone, nevirapine, diflorasone, budesonide DR.
Partials excluded from the corroboration constant (mismatched form/strength or
stale): erythromycin 500 mg tablets (UK notice covers 250 mg GR, 2024),
fingolimod (Canadian reports 2022–24), ciprofloxacin 0.3% (stale ophthalmic
bulletin), dexmethylphenidate IR (current ASHP bulletin covers ER capsules),
propafenone ER (Canadian report covers IR tablets).

Notes carry the exact scope of every citation (adjacent strengths, resolved
statuses, registration-wall caveats) — see `src/ndcres/corroboration.py`,
whose entries this document is the recorded evidence for.

## Method

Research pass over Google-indexed bulletin/report pages (ASHP and Canada
front-ends are bot-walled; TGA per-ingredient detail pages fetched directly).
A hit requires a citable bulletin/report/notification page for the same
molecule and same-or-similar form; news-only mentions recorded but not
counted. One molecule (diflorasone) was initially missed by the fan-out and
checked separately — clean miss.

## Re-verification policy

Access dates render on every badge. Entries re-verify with the recorded gaps
re-review triggers (signals threshold changes; top-10 composition shifting by
more than half week-over-week) — never a wall-clock timer.
