# /gaps quality-gate review — 2026-08-13 (sweep #1)

Operator requirement: the public gap page ships only after a hand review
of the top unlisted-constraint rows against raw data ("we need to get it
perfect"). This is that review's record.

## Scope

Sweep #1 (data vintage 2026-08-12): 2,894 classes — 377
evidence-consistent-with-supply-constraint with zero FDA listing, 179
fda-listed, 1,215 mixed, 1,123 quiet.

## Statistical scan (top 50 unlisted-constraint rows)

- 0 rows with surveyed_count < 3 — the tiny-sample dropout guard holds.
- 14 rows carry `RAW:` strength keys (unparsed upstream strengths) —
  display handled: the page renders them verbatim labeled "(as filed)".
- 1 row with null drift (fired on volume + dropout + recalls) —
  legitimate: a class can be constrained without a NADAC series.
- Repeated ingredients (diltiazem ×5, estradiol ×4, …) are DISTINCT
  strength/TE classes — correct per the equivalence-class key.

## Deep-check (top 6 classes, evidence lines verified against raw tables)

Every one shows the coherent constraint pattern — rising price AND
falling volume AND survey dropouts AND/OR recalls — with no FDA entry:

| class | price | volume YoY | survey dropouts | recalls |
|---|---|---|---|---|
| temozolomide 180mg | +11.3% | −24.3% | 14 of 14 | 1 |
| erythromycin 500mg | +12.4% | −24.5% | 3 of 12 | 2 |
| indomethacin ER 75mg | +15.0% | −21.7% | 3 of 10 | 4 |
| cinacalcet 60mg | +36.7% | −38.0% | 2 of 8 | 16 |
| cinacalcet 90mg | +12.6% | −47.9% | 2 of 6 | 13 |
| chlorthalidone 25mg | +15.9% | −15.8% | 4 of 36 | 2 |

Face validity: several of these (temozolomide, cinacalcet, chlorthalidone)
have independently reported real-world supply problems; the estradiol
transdermal classes — the documented anchor case — rank in the top 50 on
the same instrument.

Caveat recorded, not suppressed: a 100%-dropout class (temozolomide
180mg) can also indicate strength consolidation rather than shortage.
The probabilistic verdict language covers exactly this — evidence
consistent with constraint, never a confirmed shortage.

## Verdict

PASS — the ranked list is coherent, tiny-N artifacts are guarded, and
no row required ad-hoc suppression (none was applied; T-discipline: fix
root causes or publish honestly). The nav link ships.

Re-review trigger: any threshold change in signals.py, or a sweep whose
top-10 composition shifts by more than half week-over-week.
