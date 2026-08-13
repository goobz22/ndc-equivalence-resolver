# Validation: the signals measured against FDA's own listing history

Run 2026-08-13 against the live database (all sources fetched 2026-08-13;
NADAC price history 2018-12→2026-08, 10.67M rows; Medicaid SDUD volumes
2018→2026Q1, 926K rows; FDA-list history reconstructed from 98 Internet
Archive captures of the legacy `Drugshortages.cfm` CSV, 2019-10→2026-07,
61,980 rows — the same reconstruction method HHS/ASPE used, necessary
because FDA deletes resolved records instead of keeping history).

## Headline result

For every drug FDA first posted to its shortage list since 2020-01-01:

| metric | value |
|---|---|
| listings recovered | 1,090 |
| mapped to TE-rated equivalence classes | 796 (294 unmapped — see limitations) |
| **concordant at posting** (≥2 independent evidence axes already firing the day FDA first listed) | **261 (33% of mapped)** |
| of those, firing EARLY (before the posting) | 217 (83% of concordant) |
| **median lead time** | **112 days** |
| p25 / p75 / max lead | 56 / 336 / 364 days (max is CAPPED by the 364-day lookback — the true tail is longer) |

Context from the published literature: FDA's own materials document
ASHP-before-FDA listing lags of 114 and 129 days for known cases
(fda.gov/media/179066). This instrument — using entirely different,
fully public signals (acquisition-price drift, price-survey dropout,
dispensed-volume shocks, recalls) — independently measures a median
112-day lead on a fifty-times-larger sample.

## What this validates

1. **The lag is real and measurable**: one third of everything FDA
   eventually listed was already visible in public data, typically a
   quarter to a year earlier.
2. **The unlisted-constraint list deserves attention**: the same
   instrument currently flags 377 classes with the constraint pattern
   and no FDA listing (vs 179 listed) — see /gaps. Given how often the
   pattern preceded real listings historically, "unconfirmed" is the
   honest word for these — never "false positives." The FDA list is
   not ground truth; that is the finding. The estradiol transdermal
   class is the worked example: flagged here, absent from the FDA list,
   and independently listed by three mandatory-reporting regimes abroad
   (docs/dossiers/).

## Method (SPEC §13; reproduction commands below)

1. Recover FDA's listing history: `ndcres backtest fetch-history`
   (Internet Archive CDX → the legacy CSV captures; the per-row
   "Initial Posting Date" is FDA's own first-listing date).
2. Map each listed drug name to TE-rated equivalence classes
   (conservative: every ingredient term must appear in the name).
3. Replay the four evidence axes at cutoffs using ONLY rows whose
   dataset-internal dates precede the cutoff (no post-cutoff leakage —
   pinned by test).
4. Concordance = ≥2 axes firing at the posting date; lead time = the
   deepest 28-day step backward at which ≥2 axes still fire (≤364 days).

Thresholds are imported from `signals.py` — the single home — and were
NOT tuned against this history (tuning against the lagging reference
under indictment would be circular).

## Limitations (each deliberate and disclosed)

- **294 unmapped listings**: name-based mapping only reaches TE-rated
  classes; many listings are injectables/biologics/unrated products.
  The instrument's scope is retail substitutable classes — exactly
  where a consumer can act on the answer.
- **Dropout axis is a proxy in replay**: yearly NADAC files carry
  effective-date fidelity but not the original weekly as-of
  observations, so historical dropout = a ≥8-week stall in a member's
  rate-change cadence. The live pipeline uses true as-of observations.
- **Lead times are right-censored at 364 days** (the lookback cap) and
  quantized to 28-day steps.
- **Concordance ≠ causation**: the axes measure market symptoms;
  a price spike without a listing can have other causes. That is why
  every surface says "evidence consistent with," never "confirmed."

## Reproduce

```console
$ uv run ndcres refresh --nadac-years 8 --sdud-years 8
$ uv run ndcres backtest fetch-history
$ uv run ndcres backtest lead-times --since 2020-01-01 --json
```
