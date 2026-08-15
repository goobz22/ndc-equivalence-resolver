# State substitution-law research pass — evidence record (2026-08-14)

The `STATE_RULES` table in `src/ndcres/statelaw.py` was compiled by a
dedicated research pass over all 51 US jurisdictions. This document records
the method and the verification outcome; the table itself (statute citations,
URLs, override mechanisms, consent/notification/refusal flags) IS the
product, pinned by tests/test_statelaw.py.

## Verification standard and outcome

Standard: each row verified against the STATUTE TEXT itself (official
legislature site, or a named mirror — FindLaw/Justia/Cornell — where the
official site blocks automated fetching), or failing that, two agreeing
citable secondary sources. NABP's license-restricted survey was never used.

**Outcome: 51 of 51 resolved — 48 statute-verified, 3 by two agreeing
secondary sources (AL, CT, OK), 0 unverified.**

Planned classification layers that fell away in execution: the CT OLR report
2013-R-0071 turned out to cover only New England + NJ/NY (not 50 states as
planned), and the Sacks JAMA IM 2020 per-state table lives in unfetchable
figures — so statutes were fetched directly for every state, which is the
stronger posture anyway. Sacks remains cited as the cross-check layer where
its coding is discussed.

## Headline classification

- **Mandatory substitution (17)**: FL, HI, KY, ME, MA, MN, MS, NV, NJ, NY,
  PA, RI, TN, VT, WA, WV, WI — all verified from statutory "shall" language.
- **Permissive (34)**: everything else, with notable structures: Indiana is
  mandatory ONLY for Medicaid/CHIP/Medicare fills (why some surveys code it
  mandatory); DC and Michigan become mandatory upon purchaser request;
  Alabama and Delaware are opt-IN (substitution needs affirmative prescriber
  authorization).
- **Affirmative patient consent required (6)**: AK, LA, OK (prescriber OR
  purchaser authority), SC, TX (pharmacist must ask the patient to choose),
  UT.
- **No patient veto in statute (2)**: NY (only the prescriber's 'daw' blocks
  substitution), MA (recourse is a consumer-affairs complaint). RI's refusal
  must be in writing; NV's refusal right is extinguished when a government
  agency pays.

## Corrections to stale secondary tables (why statute-first matters)

1. **Wyoming flipped mandatory→permissive in 2017** (SF0121 changed "shall"
   to "may") — any survey based on pre-2017 data misclassifies it.
2. **Idaho repealed its old § 54-1723 scheme**; the current home is
   § 54-1733B (2025 pharmacy-act rewrite).
3. **Alaska renumbered**: the substitution rule now sits at § 08.80.295
   (§ 08.80.294 is now labeling).
4. **Iowa's 2024 rewrite** stripped § 155A.32 to a bare therapeutic-
   substitution clause with notification delegated to Board rules — the
   notification flag is honestly `None` (unknown).

## Fetch-blocking notes

Official sites that block automated fetching (HI capitol, NV/NJ/NM/ND/PA/
TN/TX/UT official pages) were verified via FindLaw/Justia/Cornell mirrors of
the statute text; the table stores the official-site URL where one exists
even when it is bot-unfetchable, preferring the canonical citation for human
readers.

## Maintenance policy

State law changes by legislative session, not by data refresh. The `as_of`
date renders on every use. Re-verification is event-driven: a user report, a
noticed statute amendment, or the next deliberate review pass — and any row
that falls into doubt flips to `substitution='unverified'` (the UI then
falls back to the generic sentence) rather than shipping a stale claim.
