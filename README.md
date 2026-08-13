# NDC Equivalence Resolver

> "My pharmacy says my drug is out. What is the same drug, from a different
> manufacturer, that they might actually have — and what does my prescriber
> need to write to unlock it?"

`ndcres` is an offline-first Python package + CLI that answers that question
from **public data only**: the FDA NDC Directory, the FDA Orange Book, RxNorm
(the credential-free Prescribable Content release), openFDA drug shortages,
and NADAC weekly pharmacy acquisition costs. It resolves any NDC (National
Drug Code) into ranked, tiered, source-cited substitutable alternatives, each
annotated with therapeutic-equivalence codes, manufacturer, marketing status,
package configuration, price signals, and supply-stress indicators.

**This tool is not medical advice.** It surfaces *supply-chain* equivalence
facts from public regulatory data. Anything beyond a direct
pharmacist-substitutable equivalent is explicitly labeled as requiring
prescriber authorization. Substitution decisions belong to your pharmacist
and prescriber.

**Live:** consumer UI at
[ndc-equivalence-resolver.vercel.app](https://ndc-equivalence-resolver.vercel.app)
· JSON API at
[ndcres-api.vercel.app](https://ndcres-api.vercel.app/api/resolve/0378-4642-26)
(`/api/resolve/{ndc}`, `/api/explain/{a}/{b}`, `/api/signal/{ndc}`,
`/api/search?q=`, `/api/meta`) — both refreshed weekly from the sources by
[CI](.github/workflows/data-refresh.yml); deployment architecture in
[docs/DEPLOY_NOTES.md](docs/DEPLOY_NOTES.md).

## The problem, concretely

A patient is prescribed an estradiol transdermal patch, twice-weekly,
0.05 mg/day, 8 patches per carton. She receives NDC `0378-4642-26`
(Mylan/Viatris). That NDC goes on intermittent back order; two pharmacy
chains report "out of stock" and she loses months of therapy. Meanwhile
`65162-993-08` (Amneal's **Dotti**) is the same active ingredient, same
strength, same schedule, same carton — from a different manufacturer on a
different supply channel, and FDA-rated **therapeutically equivalent**
(both are `AB1`). The pharmacy system was asked "do you have
`0378-4642-26`?" and answered honestly: no. Nothing in the retail chain
holds the equivalence graph.

That graph exists — it is just split across four federal datasets that
don't share a join key. `ndcres` builds it locally.

## The trap this tool exists to catch (a true story about its own spec)

The project brief for this tool listed **Lyllana** (`65162-149-08`,
Amneal) as a direct substitute for the Mylan anchor, alongside Dotti.
It is not — and the real Orange Book proves it:

| TE group | Reference product | 0.05 mg/day members |
|---|---|---|
| **AB1** (heading `SYSTEM;TRANSDERMAL`) | Vivelle-Dot | Mylan `0378-4642` · **Dotti** `65162-993` · Zydus `70710-1193` · Sandoz AG `0781-7144` |
| **AB2** (heading `FILM, EXTENDED RELEASE;TRANSDERMAL`) | Climara (once-weekly) | Mylan `0378-3350` · Zydus `68382-326` · Sandoz AG `0781-7133` |
| **AB3** (heading `FILM, EXTENDED RELEASE;TRANSDERMAL`) | Minivelle | **Lyllana** `65162-149` · Mylan `0378-4621` |

Dotti and Lyllana are both Amneal, both twice-weekly, both 0.05 mg/day,
both 8-count cartons — and they are **not therapeutically equivalent to
each other**, because patch matrix designs differ in ways that affect
delivery. The FDA's rule ([Orange Book preface][preface]):

> "Drugs coded with a three-character code under a heading are considered
> therapeutically equivalent only to other drugs coded with the same
> three-character code under that heading."

Nothing in the NDC, the label name, the strength, the manufacturer, or the
package reveals this. Only the application-number join into the Orange
Book does. Mylan itself markets **three** estradiol patch products in
three different TE subgroups. A resolver that flattens `AB1`/`AB2`/`AB3`
into "AB" — as the original spec accidentally did — emits swaps a
pharmacist will reject. `ndcres` treats the subscript as a hard partition
boundary, and its golden test suite encodes this exact family.

[preface]: https://www.fda.gov/drugs/development-approval-process-drugs/orange-book-preface

## Install

Requires Python ≥ 3.12. The core has **zero third-party runtime
dependencies** (stdlib only).

```console
$ git clone https://github.com/goobz22/ndc-equivalence-resolver
$ cd ndc-equivalence-resolver
$ uv sync            # or: pip install -e .
$ uv run ndcres --help
```

## Usage

### 1. Pull the data (network; ~280 MB across five public sources)

```console
$ ndcres refresh
```

Re-running is idempotent. `--source ndc|orangebook|rxnorm|nadac|shortage`
refreshes one source; `--from-dir DIR` ingests pre-downloaded files with
no network at all. Everything lands in a local SQLite database
(`~/.ndcres/ndcres.db`, override with `--db` or `NDCRES_DB`).

### 2. Resolve an NDC into ranked alternatives

```console
$ ndcres resolve 0378-4642-26
```

Real output against the live datasets (2026-08-12 vintage), trimmed to
the interesting rows:

```text
Seed: 0378-4642-26  Estradiol - Mylan Pharmaceuticals Inc.
      TE AB1 | 2/wk | NADAC $7.98/unit (seen 2026-08-12) | not on FDA shortage list
      SUPPLY-STRESS 0.12 (heuristic, not availability)
        - price-drift: acquisition cost 6.85607 (eff 2025-06-18) -> 7.97659
          (eff 2026-07-22): +16.3% over the trailing year

SUPPLY PICTURE for this drug's equivalence class (8 products):
  >> NOT on FDA's shortage list, but two or more independent public signals
     show the pattern of a supply constraint. FDA's list is manufacturer-
     self-reported and lagging; treat this drug as hard to fill and take
     the full equivalents list to the pharmacy.
     - FDA's official shortage list: no entry for any class member
     - class acquisition cost +16.3% over the trailing year on the
       CMS-damped NADAC index (generics are class-priced, so this is the
       whole class moving)
     - 0 of 5 surveyed class members have stopped appearing in the weekly
       NADAC pharmacy survey (>= 8 weeks)
     - national Medicaid dispensed volume for the class: +76.0% in 2026Q1
       vs the same quarter a year earlier (a demand surge of this size
       strains manufacturing capacity - the classic setup for backorders)
     - 2 recall record(s) against class members in the openFDA enforcement
       data (trailing two years)

TIER 1 - direct substitutes (pharmacist-level swap in most states)
    66758-147-83  Vivelle-Dot - Sandoz Inc
       TE AB1 | 8-count | 2/wk | NADAC $18.41/unit (eff 2026-07-22, seen 2026-08-12) | not on FDA shortage list
    65162-993-08  DOTTI - Amneal Pharmaceuticals LLC
       TE AB1 | 8-count | 2/wk | NADAC $7.98/unit (eff 2026-07-22, seen 2026-08-12) | not on FDA shortage list
       supply-stress 0.12 (heuristic, not availability)
         - price-drift: acquisition cost 6.85607 (eff 2025-06-18) -> 7.97659 (eff 2026-07-22): +16.3% over the trailing year
    0781-7144-83  Estradiol - Sandoz Inc
       TE AB1 | 8-count | 2/wk | NADAC $7.98/unit (eff 2026-07-22, seen 2026-08-12) | ...
    70710-1193-8  Estradiol - Zydus Pharmaceuticals USA Inc.
       TE AB1 | 8-count | 2/wk | NADAC $7.98/unit (eff 2026-07-22, seen 2026-08-12) | ...
    72162-2034-2  DOTTI - Bryant Ranch Prepack
       TE AB1 | 8-count | 2/wk | no NADAC record | not on FDA shortage list
    69238-1631-7  Estradiol - Amneal Pharmaceuticals NY LLC ...
    70771-1565-8  Estradiol - Zydus Lifesciences Limited ...

TIER 3 - requires prescriber authorization
    These need a NEW or AMENDED prescription naming the product - ask the prescriber.
    ...
    65162-149-08  LYLLANA - Amneal Pharmaceuticals LLC
       TE AB3 | 8-count | 2/wk | NADAC $7.98/unit (eff 2026-07-22, seen 2026-08-12) | not on FDA shortage list
       [different-te-subgroup] The two products carry DIFFERENT therapeutic-equivalence
       codes, so the FDA has not rated them interchangeable. Orange Book preface:
       "Drugs coded with a three-character code under a heading are considered
       therapeutically equivalent only to other drugs coded with the same
       three-character code under that heading."
    50419-451-04  Climara - Bayer HealthCare Pharmaceuticals Inc.
       TE AB2 | 4-count | 1/wk | NADAC $18.27/unit (eff 2026-07-22, seen 2026-08-12) | ...
       [different-te-subgroup] ...
       [different-schedule] The application schedules differ (e.g. twice-weekly vs
       once-weekly) - dosing and monthly quantity change.
    ...

TIER 4 - different delivery form (informational; clinical decision)
    24658-702-01  ESTRADIOL - PURACAP LABORATORIES, LLC
       TE AB | 100-count | NADAC $0.06/unit (eff 2026-07-22, seen 2026-08-12) | ...
    ... (gels, sprays, oral tablets)
```

Notice what the live data shows. This drug ran a real, months-long
shortage — pharmacies took weeks to fill, mail-order went out of stock —
and **FDA's official shortage list never carried a single record for it**
(that list is manufacturer-self-reported and lagging). The supply-picture
verdict finds the constraint anyway, by triangulating independent public
evidence: the class-priced acquisition cost climbing +16% on a damped
index, Medicaid dispensed volume up +76% year over year (a demand surge
outrunning manufacturing), and recalls against class members. Meanwhile
Lyllana, listed by this project's own brief as a direct substitute, sits
in Tier 3 where the Orange Book actually puts it.

Tiers, in order:

- **Tier 1 — direct substitutes.** Same TE subgroup (full three-character
  code), same strength, same schedule, same package size, currently
  marketed. Pharmacist-substitutable in most states without prescriber
  contact.
- **Tier 2 — same drug, different package.** Needs a quantity change on
  the prescription.
- **Tier 3 — requires prescriber authorization.** Same molecule and form,
  but a different TE subgroup, schedule, or strength. Each result carries
  machine-readable reason codes (`different-te-subgroup`,
  `different-schedule`, `different-strength`, …) and explicit
  what-to-ask-for language.
- **Tier 4 — different delivery form** (gel, spray, oral). Informational
  only; switching routes is a clinical decision.

Within each tier, results rank by supply-stress (least stressed first),
NADAC survey recency, then price. `--json` emits the whole structure.

### 3. Explain why two NDCs are (or aren't) equivalent

```console
$ ndcres explain 00378-4642-26 65162-149-08
```

(Both the brief's HIPAA spelling `65162-0149-08` and the as-filed
`65162-149-08` are accepted.) Real output:

```text
Comparing 0378-4642-26 (Estradiol) with 65162-149-08 (LYLLANA)

  [=] active ingredient(s)
      A: ESTRADIOL
      B: ESTRADIOL
      source: FDA NDC Directory, SUBSTANCENAME
  [=] delivery form family
      A: patch
      B: patch
      source: curated map over NDC Directory dosage form + route
  [=] strength
      A: UG24H:50
      B: UG24H:50
      source: NDC Directory strength, canonicalized (matches Orange Book spelling)
  [x] TE code (Orange Book)
      A: AB1 under [ESTRADIOL; SYSTEM;TRANSDERMAL] via ANDA201675
      B: AB3 under [ESTRADIOL; FILM, EXTENDED RELEASE;TRANSDERMAL] via ANDA211396
      source: Orange Book products.txt via application-number join
  [=] application schedule
      A: 2/wk (via rxnorm-scd)
      B: 2/wk (via rxnorm-scd)
      source: derived: RxNorm concept name / package wear duration / NADAC description / brand map
  [=] package size
      A: 8 x patch
      B: 8 x pouch
      source: NDC Directory package description, parsed

VERDICT: REQUIRES PRESCRIBER AUTHORIZATION - same medicine family, but NOT
an automatic substitute. A prescriber must write a new or amended
prescription naming this product.
  [different-te-subgroup] ...
```

Six dimensions, five equal — and the one that differs is the one nothing
in the retail chain surfaces.

### 4. Supply-stress signals for one NDC

```console
$ ndcres signal 0378-4642-26
```

Real output:

```text
Supply-stress signals for 00378464226 (00378-4642-26)
  NADAC survey horizon: 2026-08-12
  [ quiet] shortage (+0.000)
           not on FDA's official drug-shortage list (openFDA) - that list is
           manufacturer-self-reported and lagging; real-world pharmacy
           backorders often appear late or never, so absence is weak evidence
           and never evidence of availability
  [ quiet] survey-dropout (+0.000)
           present in the NADAC survey through 2026-08-12
  [FIRING] price-drift (+0.117)
           acquisition cost 6.85607 (eff 2025-06-18) -> 7.97659 (eff 2026-07-22):
           +16.3% over the trailing year - sustained climb on a 3-month-damped
           index; NADAC class-prices interchangeable generics, so this reflects
           the whole equivalence class tightening
  score: 0.12 of 1.00 (heuristic, not availability)
```

Per-NDC components, each with citable evidence:

| component | weight | fires when |
|---|---|---|
| shortage | 0.50 | an openFDA record with status Current / To Be Discontinued. Deliberately NOT the dominant signal: FDA's list is manufacturer-self-reported and misses whole real shortages |
| survey-dropout | 0.25 | the NDC stops appearing in weekly NADAC surveys (≥ 4 weeks behind the dataset horizon) — derived from real pharmacy invoice transactions, this often *precedes* a shortage bulletin |
| price-drift | 0.25 | trailing-12-month acquisition cost up ≥ 10% (the NADAC index is damped by a 3-month moving average, so sustained movement on it understates the spot market) |

On top of the per-NDC score, `resolve` renders a **class-level supply
picture** over the whole legal equivalence class (interchangeable
products move together): FDA-list status, class price drift, the ratio
of surveyed class members that stopped transacting, the Medicaid
dispensed-volume trend (collapse *or* demand surge — both strain
supply), and recalls against class members. Two or more independent
fingerprints yield *"evidence consistent with a supply constraint"* —
deliberately probabilistic wording. Nothing anywhere is ever a statement
of availability, in either direction.

## Data sources

All US-government public data, fetched at refresh time. **Nothing is
redistributed with this repository.**

| Source | What it contributes | License |
|---|---|---|
| [FDA NDC Directory](https://www.fda.gov/drugs/drug-approvals-and-databases/national-drug-code-directory) (`ndctext.zip`) | every listed NDC, labeler, strength, form, marketing dates | US public domain |
| [FDA Orange Book](https://www.fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files) (EOBZIP) | **therapeutic-equivalence codes**, applications, RLD/RS flags | US public domain |
| [RxNorm Current Prescribable Content](https://www.nlm.nih.gov/research/umls/rxnorm/docs/prescribe.html) | clinical-identity graph, NDC ↔ RXCUI, wear-duration evidence | no license required (the full RxNorm release is UTS-gated and deliberately **not** used) |
| [openFDA drug shortages](https://open.fda.gov/apis/drug/drugshortages/) (bulk export) | manufacturer-reported shortage records | CC0/public domain |
| [openFDA drug enforcement](https://open.fda.gov/apis/drug/enforcement/) (bulk export) | recall records — supply shocks against a class | CC0/public domain |
| [NADAC](https://data.medicaid.gov/) (data.medicaid.gov) | weekly real pharmacy acquisition costs per NDC | US public domain |
| [Medicaid State Drug Utilization](https://data.medicaid.gov/) | quarterly dispensed volume per NDC (aggregated to national at ingest) — the demand axis | US public domain |

Courtesy note: this product uses publicly available data from the U.S.
National Library of Medicine (NLM), National Institutes of Health; NLM is
not responsible for the product and does not endorse or recommend it.

## How it works

```
ingest  →  five source mirrors in SQLite (cp1252 NDC Directory, ~-delimited
           Orange Book, RxNorm RRF line-filters, NADAC CSV history,
           shortages bulk JSON), every row carrying provenance
link    →  materialized NDC↔Orange-Book join via application number +
           canonical strength (exact-decimal µg/24hr), with per-product
           link status — never a query-time fuzzy match
resolve →  equivalence group = (ingredient set, OB heading, strength,
           full TE code); a blank TE code never forms a group; schedule
           is a derived attribute with a five-rung evidence ladder and
           conflict flags; pure tier assignment with additive reason codes
```

Notable upstream realities the code handles (each pinned by a test):
NDCs come in three as-filed shapes (`4-4-2`/`5-3-2`/`5-4-1`) and
hyphen-stripping is lossy; a bare 10-digit NDC is inherently ambiguous;
`product.txt` is cp1252, not UTF-8; Orange Book strengths can embed a
`**Federal Register determination …**` suffix; Menostar's NDC Directory
entry carries the wrong application number (special-cased, with the
verbatim value preserved); discontinued brands vanish from the NDC
Directory rather than being end-dated; the schedule (twice- vs
once-weekly) exists in no structured field anywhere and is derived from
five evidence sources; and RxNorm's clinical concepts deliberately span
TE subgroups, so RxNorm is used as the identity layer, never the
substitutability oracle.

## Pharmacist substitution, in one paragraph

In nearly every US state a pharmacist may perform drug product selection —
dispensing a therapeutically equivalent generic in place of the prescribed
brand — without contacting the prescriber, provided the substitute carries
an FDA "A" rating in the same TE subgroup and is the same active
ingredient, dosage form, and strength. States differ on whether
substitution is permissive or mandatory and on patient-consent rules, and
all honor a prescriber's "dispense as written". Anything that changes the
strength, dosage form, route, or dosing schedule falls outside
substitution authority and requires a new or amended prescription — which
is exactly the boundary between Tier 1 and Tier 3 in this tool. The FDA
itself notes that Orange Book TE evaluations are public information and
advice, not legal actions.

## Development

The entire application is specified in **[docs/SPEC.md](docs/SPEC.md)** — domain
model, sources, tiering semantics, signals, API contracts, deployment — with an
invariant→test traceability table whose references are mechanically enforced
(`tests/test_spec_crosswalk.py`). A change is complete only when its spec
section and pinning tests land in the same commit as the code.

```console
$ uv sync --group dev --all-extras
$ uv run pytest          # fully offline — fixtures are byte-exact slices
                         # of the real files (see tests/fixtures/generate.py)
$ uv run mypy src        # strict
$ NDCRES_LIVE=1 uv run pytest -m live   # network smoke tests (invariants only)
```

The golden fixtures encode the estradiol family exactly as the real data
has it — including the AB1/AB2/AB3 partition, the 10↔11-digit
normalization traps, the twice-/once-weekly derivation, a planted NADAC
dropout, and a planted (clearly-synthetic) estradiol shortage record,
since no real one exists as of 2026-08.

## Roadmap

- ✅ Web UI (Next.js) with a printable "what to ask your prescriber"
  note — live at
  [ndc-equivalence-resolver.vercel.app](https://ndc-equivalence-resolver.vercel.app).
- ✅ Weekly automated data refresh publishing a ready-made database
  artifact (the rolling [`data` release](https://github.com/goobz22/ndc-equivalence-resolver/releases/tag/data))
  and redeploying the API with it.
- Geographic layer (NPPES pharmacy registry) and a path-search stretch
  goal: given location, insurance, and days-supply, the highest-probability
  route to a filled prescription.
- FDA moves to uniform 12-digit NDCs on 2033-03-07; the format layer is
  isolated in `src/ndcres/ndc.py`.

## License

MIT © Matthew Goluba
