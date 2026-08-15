# Signals quality re-review — the 5-axis assessment (2026-08-15)

Trigger: the recorded re-review clause ("any threshold change in signals.py")
fired on the Phase-3 signal changes: dropout disambiguation + the
directory-exit axis (fingerprints 4→5).

## What was reviewed, and what the review caught

**Sweep #2** (first run under the new code) moved 377→449 unlisted-constraint
classes — more than the disambiguation alone could explain. Spot-checking new
top-50 entrants caught a real instrument bug the planted tests could not:

> **The deep 8-year NADAC ingest (done for the backtest) silently changed the
> live dropout axis's meaning.** Members that left the price survey YEARS ago
> (long-departed relabelers) suddenly counted as "dropouts": montelukast
> 10 mg went surveyed 32→40, dropouts 2→10 with ZERO discontinuations — all
> eight new "dropouts" were ancient departures newly visible in the deeper
> history. The axis was designed and validated against a ~2-year window; its
> semantics depended on how much history happened to be ingested.

Fix (in the same phase): an explicit recency bound
(`_CLASS_DROPOUT_MAX_WEEKS = 104`) — a member whose last survey appearance is
older than two years is ancient history, treated like never-surveyed
(excluded from both ratio terms). Pinned by a planted test that pushes a
member's survey presence five years back and asserts it leaves the
denominator without becoming a dropout.

## Sweep #3 (recency-bounded) vs sweep #1 (4-axis baseline)

| measure | sweep #1 | sweep #2 (confounded) | sweep #3 (final) |
|---|---|---|---|
| unlisted-constraint | 377 | 449 | **413** |
| fda-listed | 179 | 179 | 179 |
| top-10 overlap vs #1 | — | 7/10 | **9/10** |
| top-50 overlap vs #1 | — | 37/50 | **44/50** |

The residual +36 constraint classes are the honest effect of the
discontinuation fix: end-marketed-but-still-priced members no longer dilute
the dropout denominator (500 classes carry 1,373 formally discontinued
members; live verification earlier showed 97% of actual dropout members are
still-marketed — the axis's validity claim). Classes that LEFT constraint
(19) are ones whose "dropouts" were discontinuations — the fix working in
both directions.

Anchor sanity: the estradiol AB1 class reads
evidence-consistent-with-supply-constraint at 3 fingerprints in all three
sweeps. Directory-exit remained None everywhere (no membership snapshots in
the local db yet — the axis goes live as the weekly pipeline accumulates
them; the accumulating state renders honestly).

## Precision-audit continuity

The Phase-2 audit was performed against sweep #1's top 50. With 44/50
retained in sweep #3's top 50, the corroboration entries (keyed on class
keys, not ranks) remain attached and correct; the measured 28/50 lower bound
still refers to the audited cohort and is dated as such.

## Verdict

PASS with the recency-bound fix included. The re-review process caught an
instrument-semantics bug that no planted test could have (it lived in the
interaction between an ingest decision and a signal definition) — recorded
here per the audit-the-instrument discipline.

Re-review triggers (restated): any threshold change in signals.py, or a
sweep whose top-10 composition shifts by more than half week-over-week. NEW
trigger added: the directory-exit axis's first four live firings get
individually verified before the axis is trusted in headlines.
