# Validation: the signals measured against FDA's own listing history

Run 2026-08-13 against the live database (all sources fetched 2026-08-13;
NADAC price history 2018-12→2026-08, 10.67M rows; Medicaid SDUD volumes
2018→2026Q1, 926K rows; FDA-list history reconstructed from 98 Internet
Archive captures of the legacy `Drugshortages.cfm` CSV, 2019-10→2026-07,
61,980 rows — the same reconstruction method HHS/ASPE used, necessary
because FDA deletes resolved records instead of keeping history).

## Headline result

For every drug whose FIRST-EVER FDA posting falls on or after
2020-01-01 (drugs first listed earlier are excluded outright — a
re-listing must never masquerade as a first posting; review-caught,
fixed with a HAVING aggregate, and re-measured):

| metric | value |
|---|---|
| first listings since 2020 | 1,011 |
| mapped to TE-rated equivalence classes | 734 (277 unmapped — see limitations) |
| **concordant at posting** (≥2 independent evidence axes already firing the day FDA first listed) | **246 (33.5% of mapped)** |
| of those, firing EARLY (before the posting) | 207 (84% of concordant) |
| **median lead time** | **112 days** |
| p25 / p75 lead | 56 / 336 days |
| right-censored | 51 cases still firing at the 364-day lookback cap — their true leads are LONGER than measured |

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

## Forward precision (added 2026-08-14)

The backtest above validates BACKWARD (signals vs FDA's own past listings).
The forward check audits the CURRENT output: of the top 50 unlisted-constraint
classes in sweep #1, **28 (56%) are independently listed by at least one other
public shortage regime** (ASHP, or the mandatory-reporting lists of Australia,
Canada, or the UK) for the same molecule and form — a lower bound, since at
least 8 of the 17 clean-miss molecules are US-only niche products the foreign
regimes never carry. Full worksheet, per-class citations, and the misses
recorded honestly: docs/dossiers/2026-08-gaps-precision-audit.md; the citation
constants live in src/ndcres/corroboration.py and render on /gaps as
"also listed by" badges (citation-only — they never feed a verdict; pinned by
test).

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

- **277 unmapped listings**: name-based mapping only reaches TE-rated
  classes; many listings are injectables/biologics/unrated products.
  The instrument's scope is retail substitutable classes — exactly
  where a consumer can act on the answer.
- **Name mapping over-matches combination products**: a class matches
  when its ingredient terms appear in the listed name, so "Ethinyl
  Estradiol and Norethindrone" also pools plain-estradiol classes into
  the replay. Per-case class/member counts are in the JSON output for
  inspection; the error direction inflates member pools, not dates.
- **Dropout axis is a proxy in replay**: yearly NADAC files carry
  effective-date fidelity but not the original weekly as-of
  observations, so historical dropout = a ≥8-week stall in a member's
  rate-change cadence. The live pipeline uses true as-of observations.
- **Publication lag can INFLATE measured leads**: the replay keys on
  dataset-internal dates (SDUD quarter, recall initiation), but a Q1
  utilization row is not publicly posted until months later, and a
  recall's initiation date precedes its public posting. A real-time
  user of this instrument would have seen some of these signals later
  than the replay assumes. The price axes (weekly NADAC) carry days of
  lag, not months.
- **Lead times are right-censored at 364 days** (the lookback cap; 51
  cases hit it) and quantized to 28-day steps.
- **Concordance ≠ causation**: the axes measure market symptoms;
  a price spike without a listing can have other causes. That is why
  every surface says "evidence consistent with," never "confirmed."

## Reproduce

```console
$ uv run ndcres refresh --nadac-years 8 --sdud-years 8
$ uv run ndcres backtest fetch-history
$ uv run ndcres backtest lead-times --since 2020-01-01 --json
```
