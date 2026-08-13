# Supply evidence: Estradiol — SYSTEM;TRANSDERMAL — UG24H:50 — TE AB1

Representative NDC: 00378464226. Class verdict: **evidence-consistent-with-supply-constraint**.

> NOT on FDA's shortage list, but two or more independent public signals show the pattern of a supply constraint. FDA's list is manufacturer-self-reported and lagging; treat this drug as hard to fill and take the full equivalents list to the pharmacy.

## The class (fetched 2026-08-13, Orange Book fetched 2026-08-13)

| NDC | product | labeler | application | TE | marketed |
|---|---|---|---|---|---|
| 0378-4642-26 | Estradiol | Mylan Pharmaceuticals Inc. | ANDA201675 | AB1 | yes |
| 66758-147-83 | Vivelle-Dot | Sandoz Inc | NDA020538 | AB1 | yes |
| 72162-2034-2 | DOTTI | Bryant Ranch Prepack | ANDA211293 | AB1 | yes |
| 69238-1631-7 | Estradiol | Amneal Pharmaceuticals NY LLC | ANDA211293 | AB1 | yes |
| 70771-1565-8 | Estradiol | Zydus Lifesciences Limited | ANDA206241 | AB1 | yes |
| 65162-993-08 | DOTTI | Amneal Pharmaceuticals LLC | ANDA211293 | AB1 | yes |
| 0781-7144-83 | Estradiol | Sandoz Inc | NDA020538 | AB1 | yes |
| 70710-1193-8 | Estradiol | Zydus Pharmaceuticals USA Inc. | ANDA206241 | AB1 | yes |

## FDA shortage list (fetched 2026-08-13)

- **No entry for any of the 8 class members.** The list is manufacturer-self-reported and lagging; absence is not availability.

## Acquisition-cost trend (fetched 2026-08-13)

- Class acquisition cost **+16.3%** over the trailing year on the CMS-damped NADAC index.
- 00378464226: $5.98844 (2024-12-18) -> $7.97659 (2026-07-22), 20 rate changes on record
- 00781714483: $5.98844 (2024-12-18) -> $7.97659 (2026-07-22), 20 rate changes on record
- 65162099308: $5.98844 (2024-12-18) -> $7.97659 (2026-07-22), 20 rate changes on record
- 66758014783: $18.46775 (2025-08-20) -> $18.40548 (2026-07-22), 12 rate changes on record
- 70710119308: $5.98844 (2024-12-18) -> $7.97659 (2026-07-22), 20 rate changes on record
- 0 of 5 surveyed members have stopped appearing in the weekly pharmacy survey.

## Dispensed volume (fetched 2026-08-13)

- 2024Q1: 268,814 units (25,607 prescriptions), Medicaid national
- 2024Q2: 315,130 units (29,398 prescriptions), Medicaid national
- 2024Q3: 366,894 units (34,456 prescriptions), Medicaid national
- 2024Q4: 378,604 units (36,019 prescriptions), Medicaid national
- 2025Q1: 403,126 units (37,380 prescriptions), Medicaid national
- 2025Q2: 487,632 units (44,465 prescriptions), Medicaid national
- 2025Q3: 619,762 units (55,894 prescriptions), Medicaid national
- 2025Q4: 722,420 units (65,383 prescriptions), Medicaid national
- 2026Q1: 709,488 units (65,106 prescriptions), Medicaid national
- Year-over-year change in 2026Q1: **+76.0%**.

## Recalls (fetched 2026-08-13)

- 2024-05-16: Class III (Ongoing), product 707101193 — Failed Impurities/Degradation Specifications.
- 2024-05-16: Class III (Ongoing), product 707101193 — Failed Impurities/Degradation Specifications.

## Assessment (all inputs above)

- Independent evidence axes firing: **3 of 4** (price drift, survey dropout, volume movement, recalls).
- FDA's official shortage list: no entry for any class member (that list is manufacturer-self-reported and lagging - real shortages often never appear on it)
- class acquisition cost +16.3% over the trailing year on the CMS-damped NADAC index (spot increases run higher; generics are class-priced, so this is the whole class moving)
- 0 of 5 surveyed class members have stopped appearing in the weekly NADAC pharmacy survey (>= 8 weeks)
- national Medicaid dispensed volume for the class: +76.0% in 2026Q1 vs the same quarter a year earlier (a demand surge of this size strains manufacturing capacity - the classic setup for backorders)
- 2 recall record(s) against class members in the openFDA enforcement data (trailing two years)

## This class across sweep history

- 2026-08-13: evidence-consistent-with-supply-constraint (3 fingerprints)

## Reproduce this

```console
$ pip install uv && git clone https://github.com/goobz22/ndc-equivalence-resolver
$ uv sync && uv run ndcres refresh
$ uv run ndcres sweep
$ uv run ndcres dossier 00378464226
```

## Sources (every number above)

- FDA National Drug Code Directory — U.S. Food & Drug Administration — https://www.fda.gov/drugs/drug-approvals-and-databases/national-drug-code-directory (fetched 2026-08-13)
- FDA Orange Book (Approved Drug Products with Therapeutic Equivalence Evaluations) — U.S. Food & Drug Administration — https://www.fda.gov/drugs/drug-approvals-and-databases/approved-drug-products-therapeutic-equivalence-evaluations-orange-book (fetched 2026-08-13)
- RxNorm (Current Prescribable Content) — U.S. National Library of Medicine — https://www.nlm.nih.gov/research/umls/rxnorm/docs/prescribe.html (fetched 2026-08-13)
- FDA Drug Shortages database (via openFDA) — U.S. Food & Drug Administration — https://dps.fda.gov/drugshortages (fetched 2026-08-13)
- NADAC (National Average Drug Acquisition Cost) — Centers for Medicare & Medicaid Services — https://data.medicaid.gov/datasets?fulltext=NADAC (fetched 2026-08-13)
- Medicaid State Drug Utilization Data — Centers for Medicare & Medicaid Services — https://www.medicaid.gov/medicaid/prescription-drugs/state-drug-utilization-data/index.html (fetched 2026-08-13)
- FDA drug recall enforcement reports (via openFDA) — U.S. Food & Drug Administration — https://open.fda.gov/apis/drug/enforcement/ (fetched 2026-08-13)

*Not medical advice. Verdicts are inferences from independent public datasets — evidence consistent with a supply constraint, never a confirmed shortage and never a statement of availability. Substitution decisions belong to pharmacist and prescriber.*