# NDC Equivalence Resolver — Specification

This is the authoritative specification of the entire application. Every numbered
invariant (INV-x.y) in §19 names the test(s) that prove it; an invariant without a
passing named test is treated as unspecified. `tests/test_spec_crosswalk.py`
mechanically verifies that every referenced test exists in the collected suite.

**Standing rule:** a change is complete only when its spec section, its traceability
rows, and its tests land in the same commit as the code.

---

## 1. Purpose & positioning

**The problem.** US pharmacies stock medications by NDC — a code tied to one
manufacturer's product. When that exact code is on back order, FDA-rated equivalents
from other manufacturers often are not — and the official FDA shortage list is
voluntary, lagging, and keeps no history, so real supply strain often never appears
on it ("the measuring cup has no lines on the side of it").

**The product.** For any drug, show both:
1. **Substitutable alternatives** — what a pharmacist can swap on the spot, and what
   a prescriber could authorize (the equivalence half), and
2. **Independent supply-stress evidence** — price spikes, survey dropouts, demand
   surges, recalls — from public data, whether or not the official list has caught
   up (the supply-truth half).

The homepage hero (app/page.tsx) is the rendered form of this positioning and must
stay consistent with this section.

**Framing rules (non-negotiable):**
- Not medical advice. Substitution decisions belong to pharmacist and prescriber.
- Anything beyond a direct pharmacist-substitutable equivalent is labeled as
  requiring **prescriber authorization**.
- Supply indicators are **inferences** — "evidence consistent with a supply
  constraint" — never availability claims, never "shortage confirmed".
- Every number traceable to a public source row with a vintage.

## 2. Domain model

### 2.1 NDC formats
- Three as-filed 10-digit hyphenated shapes exist: **4-4-2, 5-3-2, 5-4-1** (all
  three occur inside the estradiol family). Each pads a different segment to reach
  the 11-digit HIPAA 5-4-2 form. The as-filed string is preserved and is the only
  displayed form; `ndc11` (hyphenless zero-padded) is the join key.
- A bare 10-digit string is **inherently ambiguous** (up to three padding
  candidates); resolution requires the database (21 CFR 207.33(b)(3): one labeler
  code uses exactly one configuration). Ambiguity is an error that lists candidates.
- 11-digit input is accepted bare, hyphenated 5-4-2, and in "brief-style"
  reconstructed hyphenation (e.g. `65162-0993-08`, which exists in no source file).
- 21 CFR 207.33 permits five configurations including native-11 6-4-1/6-3-2; none
  appear in current data; 11-digit input is treated as 5-4-2 and verified against
  the database crosswalk. (FDA moves to uniform 12-digit NDCs 2033-03-07 — the
  format layer is isolated in `src/ndcres/ndc.py`.)
- Grains: **product = ndc9** (labeler+product), **package = ndc11**.

### 2.2 Therapeutic-equivalence codes (Orange Book)
- Orange Book preface rule (quoted in explain output): *"Drugs coded with a
  three-character code under a heading are considered therapeutically equivalent
  only to other drugs coded with the same three-character code under that heading."*
  A heading = identical ingredient(s) + dosage form + route — so subscript
  namespaces (AB1/AB2/AB3) are scoped **per heading**, and the code alone is not a
  group id.
- A blank TE code means "not evaluated" — it never wildcards and never groups.
- **Equivalence-class key**: `(ingredient_set, df_route, strength_norm, te_code)`.
  NULL te_code ⇒ no eq_group; None never matches anything including itself.

### 2.3 The corrigendum (worked example, pinned by goldens)
The project brief listed Lyllana (65162-149) as a direct substitute for the Mylan
anchor 0378-4642. The real Orange Book partitions estradiol transdermal 0.05mg/day:
**AB1** = Vivelle-Dot group (incl. the anchor AND Amneal Dotti 65162-993), **AB2** =
Climara once-weekly group, **AB3** = Minivelle group (incl. Amneal Lyllana). Same
strength, same schedule, same pack — but AB1 vs AB3 is a hard partition boundary:
Lyllana is Tier 3 (`different-te-subgroup`), Dotti is Tier 1. Mylan itself has
products in AB1, AB2 and AB3 (0378-4642 vs 0378-3350 vs 0378-4621). The resolver
follows the data, not the brief.

### 2.4 Strength canonicalization
- Decimal-exact (`decimal.Decimal`, never float). Canonical forms: rate
  `UG24H:<n>` (µg/24hr), mass `UG:<n>`, gel concentration `PCT:<p>;G:<g>`.
- NDC-directory side handles leading-dot decimals (".05" + "mg/d"), microgram
  units ("14" + "ug/d"), gel concentrations. Orange-Book side handles
  "0.05MG/24HR", "EQ ... BASE" prefixes, and strips the
  ` **Federal Register determination…**` suffix (present on 2,408 real rows)
  before parsing.
- Cross-source join happens ONLY on canonical strength; rate never matches mass;
  unparseable strengths stay raw and never match.

### 2.5 Packaging & form family
- `PACKAGEDESCRIPTION` is parsed for pack count (multiplicative nesting until
  measure units) and wear-duration evidence: only `3.5 d in 1 PATCH` / `7 d in 1
  PATCH` count as schedule evidence (guards junk like Amneal's "1 d in 1 POUCH").
- Dosage-form strings are unreliable for classing; a curated cross-source
  **form-family map** (`formfamily.py`) unifies PATCH / PATCH,ER / FILM,ER / SYSTEM
  → "patch", with gels/sprays/oral distinct, and unknown forms distinct-not-None.

## 3. Data sources (all public, credential-free; the complete list)

| # | Source | What we take | Format traps (each pinned by a test) |
|---|---|---|---|
| 1 | FDA NDC Directory (`ndctext.zip`) | products + packages, marketing status, application numbers | product.txt is **cp1252**; three NDC shapes unpadded; discontinued brands are ABSENT (not end-dated); `NDC_EXCLUDE_FLAG` carries no signal |
| 2 | FDA Orange Book (`products.txt`) | applications, TE codes, strengths, RX/DISCN/OTC | `~`-delimited; FR-determination suffix inside Strength; Product_No NOT strength-ordered |
| 3 | RxNorm Prescribable Content (no-license release) | concepts, relations, NDC↔RXCUI | RRF pipe format; SCD/SBD normalization; bare-11 NDCs |
| 4 | openFDA drug shortages (bulk zip, never paginated API) | shortage records | `package_ndc` native 10-digit segmentation; literal `"Unvailable"` typo preserved; duplicate package_ndc rows legitimate; **snapshot-only** (resolved records deleted upstream) |
| 5 | CMS NADAC (per-year datasets via metastore discovery) | weekly acquisition costs | download URL rotates weekly — always resolve via metastore; quoted comma-list `explanation_code`; weekly restatements dedupe on (ndc11, effective_date) |
| 6 | Medicaid State Drug Utilization (per-year via metastore) | quarterly volumes | state aggregation; suppressed rows skipped |
| 7 | openFDA enforcement (all partitions) | drug recalls | ndc9 extraction best-effort; unindexed rows kept |

Licensing: US-government works / public domain (NADAC & SDUD carry CMS open-data
terms; RxNorm Prescribable Content is the explicitly no-license release; NLM
courtesy attribution in README). Full table in README.

## 4. Ingestion & storage

- SQLite, WAL for the local read-write store. Schema single-sourced in
  `db.py:_DDL`. `connect()` = read-write create-if-needed; `connect_readonly()`
  (mode=ro, `PRAGMA query_only`, optional `immutable=1`) is the ONLY serving path.
- **Mirror vs append**: mirror tables (product, package, ob_product, rx_*,
  shortage, sdud, enforcement, link) are atomically replaced per source refresh —
  upstream absence IS the discontinuation signal. **nadac is append-merge** on
  (ndc11, effective_date) with `as_of_first`/`as_of_last` bumping — the dropout
  signal needs history the weekly full-replacement upstream doesn't replay.
  Tables not in `MIRROR_TABLES` survive refresh (this mechanism also protects the
  Phase-3 sweep history).
- Every row carries `run_id` → `source_run` (url, sha256, fetched_at, vintage) —
  the provenance spine.
- Parsers validate headers and **fail loudly on drift** — never silently skip.
- `special_case` table corrects known upstream defects with citation; the one
  active case: Menostar 50419-455 carries Climara's NDA020375 in the NDC Directory;
  its true application is N021674. Corrections preserve the raw value.
- The OB link is a **materialized build step** (`product_ob_link`): special-cases
  first, then application join, then strength disambiguation; per-product
  `ob_link_status` ∈ linked / no-application / no-ob-row / strength-mismatch /
  ambiguous / special-cased — never guessed, surfaced in explain.
- Refresh is idempotent (double-ingest = identical content) and per-source atomic.

## 5. Equivalence & tiering

`assign_tier` is a pure function; reasons are tuples of stable codes.

- **EXCLUDED** (evaluated first; provenance-bearing notes, never ranked):
  `discontinued-ob` (OB DISCN and not marketed), `not-in-current-ndc-directory`,
  sample packages. NDC-active-but-OB-DISCN conflicts get T3 + `status-conflict`,
  not exclusion.
- **T1 Direct substitute**: same eq_group + same pack count (both non-null) +
  marketed. Schedule inherits within a group (`te-group-inherited`). Symmetric.
- **T2 Quantity change**: same eq_group, different/unknown pack config (incl. the
  seed product's other packs).
- **T3 Prescriber authorization**: same ingredient + form family, outside the
  seed's group; additive reasons: `different-te-subgroup` (emitted ONLY when the
  heading or full TE code actually differs), `different-schedule` (with 8→4/month
  note), `different-strength`, `no-te-code` / `not-in-orange-book`,
  `seed-no-te-rating` (OTC/monograph/unlinked/discontinued seeds cap everything at
  T3), `schedule-unknown` (unknown blocks T1/T2 across groups, never within).
- **T4 Different form family**: informational; clinical-decision flag; price
  ranking suppressed across pricing-unit boundaries.
- Candidate gathering = union of the OB path (same ingredient_set) and the RxNorm
  path (SCD→IN→single-ingredient SCDs; combo guard: Climara Pro's
  ESTRADIOL|LEVONORGESTREL never enters single-ingredient results).
- Seed fallbacks: package hit → full seed; ndc9-grain hit → T2 semantics; rx_ndc-
  only hit (e.g. Alora) → RxNorm-derived seed, banner, all candidates cap at T3.
- Ranking within tier: stress asc (+0.1 no-NADAC nudge) → NADAC recency desc →
  price asc → name → ndc11 (deterministic tiebreak).
- Properties pinned: tier partition (no candidate in two tiers), T1 symmetry,
  determinism, blank-TE-never-groups, seed never its own candidate.

## 6. Schedule derivation (evidence ladder)

Confidence order — highest present rung decides; conflicts flagged
(`schedule_conflict`) but never override the ladder; no evidence = unknown, never
guessed:
1. RxNorm SCD duration: `84 HR` → twice-weekly, `168 HR` → once-weekly (other
   durations are NOT mapped)
2. Package wear duration (`3.5 d`/`7 d in 1 PATCH`)
3. NADAC description markers `(2/WK)` / `(1/WK)`
4. Name marker ("Twice-Weekly") + curated brand map (DailyMed-cited)
5. Pack-count heuristic (8→2×/wk, 4→1×/wk), scoped to estradiol transdermal only
Every finding carries citable evidence detail.

## 7. Signals & class assessment

### 7.1 Per-NDC signal components (all dataset-relative; never wall-clock)
- **shortage** (weight 0.50): active openFDA record (status ∈ {Current, To Be
  Discontinued}); Resolved never fires. ABSENCE renders "not on FDA shortage
  list" with the lagging-source caveat — NEVER "available", NEVER "no shortage".
- **dropout** (weight 0.25): weeks since NDC last present in NADAC vs the dataset
  horizon (`survey_horizon`); fires ≥4 weeks, full at 8. Never-surveyed reads
  quiet, not missing-data crash.
- **drift** (weight 0.25): latest NADAC price vs the rate in force one year prior;
  fires at +10%, full at +35% (CMS 3-month damping documented).
- Stress ∈ [0,1] = weighted blend with per-component evidence lines. Reports are
  wall-clock independent (same DB ⇒ same report, any day).

### 7.2 Class supply assessment (triangulation over the legal class)
- Members = seed + T1 + T2 (the legal substitution class), deduped.
  `class_supply_assessment(conn, members, *, class_key=None)` — the key enables
  the directory-exit axis; sweep, resolve, and dossier all pass it (one
  engine).
- **Five fingerprint axes** (`FINGERPRINT_AXES = 5`, serialized so no display
  surface ever hardcodes the count):
  1. class price drift ≥ +10%;
  2. survey dropout ratio ≥ 0.25 with surveyed ≥ 3 — **scoped to
     still-marketed members**: formally end-marketed members are
     DISCONTINUATION, counted separately as `discontinued_members` and
     excluded from BOTH the numerator and the denominator (in the numerator
     they fake strain; in the denominator they dilute the ratio for exactly
     the classes where discontinuation is heaviest). **Recency-bounded**
     (`_CLASS_DROPOUT_MAX_WEEKS = 104`): a member last surveyed more than
     two years before the horizon is ancient history, treated like
     never-surveyed — without this bound the axis's meaning silently depends
     on how many years of NADAC history are ingested (caught live by the
     2026-08 re-review; docs/dossiers/2026-08-signals-rereview.md);
  3. SDUD volume decline ≤ −15% OR surge ≥ +25%;
  4. recalls within 730 days;
  5. **directory-exit** (the fast witness, §10.3): members that vanished from
     the weekly NDC directory while still RX-active and NOT end-marketed at
     last sight, within the trailing 12 weeks; fires at ≥2 (conservative v1,
     re-reviewed after four live snapshots). GUARD: without a class key or
     with fewer than two membership snapshots the axis is `None` — reported
     as "accumulating", and it can never fire or count.
- Per-axis fired flags (`drift_fired`, `dropout_fired`, `volume_fired`,
  `directory_exit_fired`) ship in the payload — display surfaces never
  re-implement thresholds.
- Verdict ladder (unchanged meaning — "two independent corroborating
  signals"): any active FDA record → `fda-listed-shortage`; ≥2 fingerprints →
  `evidence-consistent-with-supply-constraint`; exactly 1 → `mixed-signals`;
  else → `no-independent-stress-evidence` (reads "quiet", never "available").
- Verdict language lives ONLY in `VERDICT_LANGUAGE` (single home).

## 8. Search engine (`src/ndcres/search.py`)

Structured drug search: the query is parsed into CLASSIFIED tokens that AND
together across field classes, token order never matters.

- **Token classes**: NDC-ish (digits/hyphens; hyphenated forms normalize via
  ndc.py segmentation rules, bare 8-digit also tries the 4-4 shape's padding);
  strength-ish (".05", "0.05 mg", "0.05mg", "50 mcg", "0.06%" — canonical-key
  candidates generated AT QUERY TIME with the same decimal canonicalization
  ingest uses, matched exactly against `product.strength_norm`; a bare number
  covers both mg and µg readings; aliases live in the parser, never stored);
  form words ("patch", "tablet" → the curated form_family values with a raw
  dosage-form fallback); everything else is a name term over proprietary
  name+suffix, generic name, ingredient set, labeler, and best RxNorm name.
  A bare 4–7-digit number is ambiguous (NDC fragment or strength) and matches
  if EITHER interpretation does.
- **`search_doc`** (one row per ndc9; a derived mirror rebuilt after every
  refresh, like product_ob_link — and like it, deliberately no FK to product,
  which would block the mirror-replace lifecycle): best RxNorm concept name
  (SCD-preferred, the same TTY rule resolve uses), TE code, marketed flag,
  NADAC presence, representative package (min marketed non-sample ndc11),
  package count, run_id provenance. Ships in the web export.
- **Results are PRODUCT-grain** (one hit per ndc9, no duplicate-package spam),
  each carrying the representative package so result links resolve directly.
- **Ranking (deterministic)**: per name term the best field match scores
  word-exact (3) > word-prefix (2) > substring (1); +2 marketed, +0.5
  NADAC-surveyed; ties break on display name then ndc9.
- A query with an unmatchable token returns empty — never garbage.
- No FTS5 dependence (serverless SQLite builds vary); the corpus (114k
  products) serves tokenized indexed queries directly.

## 9. Provenance & attribution (`src/ndcres/provenance.py`)

Operator rule: "wherever we give data, give a source URL on the web back to
where the data was gotten from."

- **`SOURCE_REGISTRY`** (single home): per source — display name, publisher,
  landing URL, license posture — for all seven ingest sources AND the derived
  tables (link, search), so a ref is never silently missing.
  `source_refs(conn)` merges identity with the latest source_run per source
  (vintage, fetched_at, sha256); a never-ingested source still appears with
  null run state — absence is shown, never hidden.
- **Every payload carries `sources`** (resolution / explanation / signal /
  search) plus the disclaimer; `/api/meta` carries the full merged `registry`.
  The dict builders take `sources` as a required keyword so the CLI and web
  cannot drift (the parity pin covers it).
- **Deep links** where upstream schemes are stable: `ob_application_url`
  (accessdata Orange Book results per application — the primary citation for
  every TE claim, attached to every annotated row as `application_url`) and
  `rxnav_url` (per-RXCUI). Outbound citation links only — nothing is fetched.
- **UI**: `SourceTag` renders "Source: {linked names} · data fetched {date}"
  under the seed section, the SupplyPicture block, browse results, and the
  compare table; ProductCard links the FDA Orange Book record; the printable
  prescriber note carries a Data-provenance field (fetch dates + /sources
  pointer); `/sources` lists every source with publisher, license, vintage,
  and SHA-256; the site-wide legal footer states the public-domain/open-data
  status, MIT/as-is posture, probabilistic framing, and no-tracking promise.

## 10. Market sweep & longitudinal history

### 10.1 The sweep (`src/ndcres/sweep.py`, Phase 3 — landed)

- `enumerate_classes` finds every TE-rated equivalence class via
  `ob_product ⋈ product_ob_link ⋈ product ⋈ package` and applies the LEGAL-class
  membership filter that mirrors resolve's seed+T1+T2 set: sample packages
  dropped, discontinued-and-unmarketed members dropped, zero-marketed classes
  skipped entirely. Coherence is pinned: a class's members equal what resolve
  computes for a member seed — one verdict engine, two entry points, zero drift.
- `run_sweep` (pure) assesses every class with the UNCHANGED
  `class_supply_assessment`; `persist_sweep` appends one `sweep_run` row +
  per-class `sweep_class` rows (components + fingerprints + verdict; the
  verbose evidence lines are NOT persisted — regenerable, and compactness is
  what keeps the history durable at ~0.6MB/run). Tables are append-only
  (exempt from the mirror wipe — the nadac mechanism); `code_version` is
  stamped because verdicts are threshold-dependent.
- `fingerprints` (the count of independent evidence axes) is computed BEFORE
  the verdict ladder, so an fda-listed class still reports how much independent
  evidence backs the listing (the listed-but-quiet gap list depends on this).
- CLI: `ndcres sweep [--json]` — summary counts + the top unlisted-constraint
  classes, ranked (fingerprints, surveyed breadth, market breadth).
- The verdict ladder is pinned UNIVERSALLY over every swept class (not just a
  planted case): fda-listed ⇔ any active record; constraint ⇔ ≥2 fingerprints;
  mixed ⇔ 1; quiet ⇔ 0.

### 10.3 Directory-membership history (`src/ndcres/membership.py`)

The NDC Directory is a weekly full replacement: a product that vanishes from it
has left the shelf-facing record NOW — weeks before the CMS-damped price survey
notices, months before quarterly volumes do. The membership snapshot records
that fast witness:

- **`ndc_membership_state`** — one row per directory ndc11 (the rolling
  baseline), upserted each snapshot with marketing status, best-linked OB type
  (RX > OTC > DISCN), and the TE-rated equivalence-class key (via
  `sweep.enumerate_classes` — one engine; multi-class members take the
  lexicographically first key, deterministic).
- **`ndc_membership_delta`** — append-only appeared/vanished rows from the
  second snapshot on. A vanished NDC's row is stamped **from state** — the
  current database no longer holds the row, so the state table is the only
  honest witness to what it looked like at last sight.
- **`ndc_membership_run`** — one row per snapshot; date is dataset-relative
  (the ndc `source_run` fetch date; refuses loudly when nothing was ingested);
  same-date re-runs are idempotent no-ops. First run = baseline: state
  populated, ZERO delta rows (a baseline has nothing to differ from).

Snapshots write to the durable archive and the local db;
`copy_recent_deltas(history, main, window_weeks=12)` backfills the trailing
window into the fresh weekly pipeline database. None of the three tables is
mirror-wiped. The directory-exit signal axis (§7.2, when it lands) is the
consumer; until then the tables only accumulate. CLI:
`ndcres membership-snapshot [--history PATH]`; weekly workflow runs it between
the FDA-list snapshot and the sweep.

### 10.2 Longitudinal history (`src/ndcres/history.py`, Phase 4 — landed)

FDA deletes resolved shortage records instead of keeping history (HHS/ASPE had
to reconstruct the list's past from Wayback snapshots). The forward archive
accumulates that record:

- **`fda_list_history`**: weekly snapshots of what the FDA list said, derived
  from the openFDA bulk ALREADY ingested (no second fetch, no second parser to
  drift); snapshot date = the shortage source_run's fetch date
  (dataset-relative); the PK dedupes same-date re-runs.
  (Note: healthdata.gov's fnt4-gy9k entry was investigated and is only an
  href pointer to FDA's page, not a mirrorable file — deriving from our own
  vintage-stamped ingest is both simpler and honest.)
- **The durable archive `ndcres-history.db`**: the weekly runner starts from
  an empty database, so sweep verdicts and list snapshots are exactly the data
  no upstream source will replay. The pipeline downloads the archive from the
  rolling release, appends (`append_sweep_to_history` assigns fresh archive
  ids — runner-local ids all start at 1 and would collide), and re-uploads;
  quarterly dated copies (`ndcres-history-YYYYQn.db`) guard against asset
  deletion. Integrity guards throughout: `open_history` runs
  `PRAGMA integrity_check` before anything appends; a regressive append
  raises — the job fails rather than clobber-uploading a damaged archive.
- CLI: `ndcres fda-snapshot [--history PATH]` (records locally, and into the
  archive when given) and `ndcres sweep --history PATH`.
- `snapshot_source` values: `openfda-weekly` (forward) · `wayback-cfm`
  (Phase 7 historical backfill).

## 11. Evidence dossier (`src/ndcres/dossier.py`, Phase 5 — landed)

One `Dossier` dataset (class members, assessment, live FDA rows, full NADAC
series per member, SDUD quarterly trend, recalls, this class's sweep-verdict
history, provenance refs), two renderers:

- **`dossier_markdown` — the PUBLIC case study.** Operator decision #4
  enforced mechanically: every URL in the rendered markdown must be an
  ingested source's own registry page or this repository (allowlist test);
  every evidence section carries its source vintage stamp; ends with the
  "Reproduce this" commands. The demand narrative is carried by ingested
  numbers, never a news cite. Absence of an FDA record renders the
  lagging-list language, never availability.
- **`dossier_exhibits` — the petition-shaped pack** (21 CFR 10.30 structure:
  requested action, statement of grounds, evidence sections from ingested
  data, the 10.30(b) certification placeholder). External references
  (`EXTERNAL_REFERENCES` constants with URL + access date) appear ONLY after
  the "NOT pipeline data" separation banner — pinned by test. The header
  states filing is the operator's decision and a lawyer should read it first.
- Surfaces: `ndcres dossier <ndc> [--json] [--md PATH] [--exhibits PATH]`,
  `GET /api/dossier/{ndc}`, `/dossier/[ndc]` print-styled page (which states
  its web.db data limits: full NADAC series is CLI-only). Pilot artifacts for
  the estradiol class live under `docs/dossiers/`.
- Language discipline pinned: "shortage confirmed" never appears;
  "evidence consistent with" and "not medical advice" always do.

## 12. Gap report (`src/ndcres/gaps.py`, Phase 6 — landed)

- `gap_report(conn, sweep_id=None)` reads the LATEST persisted sweep — never
  recomputes at request time — and partitions every class:
  `unlisted_constraints` (constraint verdict ⇒ zero active FDA records by
  construction — the headline), `fda_listed` (concordant), and
  `listed_but_quiet` (listed with zero independent fingerprints — the
  instrument disagreeing in the other direction, shown for honesty).
- Ranking (deterministic, documented): fingerprints DESC, surveyed_count DESC
  (guards tiny-N artifacts), member_count DESC (impact proxy), drift DESC
  nulls-last, class key. SDUD units rejected as an impact weight (units are
  incomparable across dose forms).
- Surfaces: `GET /api/gaps?limit=` (404 with a helpful message when no sweep
  exists — e.g. a stale artifact), `ndcres gaps [--json]`, `/gaps` page with
  the measurement-language headline, fingerprint chips, human strength labels
  (`RAW:` keys render verbatim labeled "as filed"), row links to the resolve
  view, and source tags. Nav link shipped AFTER the quality gate.
- **Quality gate (operator: "get it perfect")**: recorded in
  docs/dossiers/2026-08-gaps-quality-review.md — statistical scan of the top
  50 (0 tiny-N rows) + deep-check of the top 6 against raw tables (all show
  the coherent price-up/volume-down constraint pattern), zero ad-hoc row
  suppression, re-review triggers named (threshold changes; >50% top-10
  composition shift week-over-week).
- **Corroboration & forward precision**: `src/ndcres/corroboration.py` holds
  curated, dated citations showing a flagged class is ALSO listed by another
  public shortage regime (ASHP / AU TGA / Canada HPS / UK DHSC) — the output
  of the recorded precision audit
  (docs/dossiers/2026-08-gaps-precision-audit.md: 28 of the top 50, a lower
  bound). CITATION-ONLY, the dossier EXTERNAL_REFERENCES posture: entries
  never feed a verdict, fingerprint, or ranking (pinned by a planted-defect
  test); rendered on /gaps as "also listed by {source} · accessed {date}"
  badges, never "confirmed". Re-verification follows the quality-review
  triggers, not a wall-clock timer. `gaps.worksheet(conn, N)` /
  `ndcres gaps --worksheet N` emits the audit worksheet, ordering pinned to
  the report.

## 13. Backtest methodology (`src/ndcres/backtest/`, Phase 7 — landed)

- **History source** (`wayback.py`): the legacy `Drugshortages.cfm` endpoint
  served the whole list as CSV; the Internet Archive holds ~45 captures
  (2019-10 → present), discovered via the CDX API and parsed with the pinned
  22-column legacy header (drift raises). Each capture lands in
  `fda_list_history` (`snapshot_source='wayback-cfm'`), including FDA's own
  per-row **Initial Posting Date** — so first-listing dates come from FDA's
  own field, not snapshot-diffing (a deliberate improvement over the plan's
  interval table, which is therefore not needed; intervals derive from
  `min(initial_posting)` per normalized name).
- **Replay** (`leadtime.py`): a listed name maps to TE-rated classes
  conservatively (every ingredient part must appear in the name); the four
  evidence axes replay using ONLY rows whose dataset-internal dates precede a
  cutoff. Thresholds are IMPORTED from signals.py — one home, never retuned
  here (tuning against the lagging reference under indictment is circular).
  Documented approximation: replayed NADAC carries effective-date fidelity,
  not the weekly as-of observations, so the dropout axis is proxied by a
  stall in rate-change cadence (≥8 weeks).
- **Metrics**: concordance-at-posting (≥2 axes firing when FDA first posted)
  and lead time (28-day steps back, ≤364-day lookback, lead = deepest step
  still firing). The unconfirmed-positive side is the SWEEP's unlisted-
  constraint count — unconfirmed, never "false": the list is not ground
  truth; that is the finding, and estradiol is the worked example.
- Depth: `refresh --nadac-years N --sdud-years N` (yearly datasets exist
  credential-free to 2013/1991). CLI: `ndcres backtest fetch-history` /
  `ndcres backtest lead-times [--since] [--json]`. Batch-only — never in the
  serving path. Results: docs/VALIDATION.md.

## 14. Web API contracts

All JSON shapes have exactly one home: `src/ndcres/serialize.py`. The web layer
must serve byte-identical structures to the CLI's `--json` (pinned by the parity
test). Serializers emit JSON-native types only (no tuples).

| Endpoint | Returns |
|---|---|
| `GET /api/resolve/{ndc}` | `resolution_dict`: seed annotation, tiers T1–T4 + excluded, class_assessment, disclaimer |
| `GET /api/explain/{a}/{b}` | `explanation_dict`: verdict + six dimension lines, every line source-cited |
| `GET /api/signal/{ndc}` | `signal_dict`: components with evidence + stress score |
| `GET /api/search?q=&limit=` | result list (Phase 1 upgrades this to grouped product grain) |
| `GET /api/meta` | per-source vintages (source_run) + disclaimer |
| `GET /api/dossier/{ndc}` | dossier payload (§11) |
| `GET /api/gaps?limit=` | gap report (§12) |
| `GET /api/classes` | canonical class index: slug + key + rep + verdict per latest-sweep class (feeds the sitemap) |
| `GET /api/class/{slug}` | one class + its full resolution via the representative package; helpful 404 for unknown/stale slugs |

Errors: unknown/unresolvable NDC → 404 with a helpful detail message; a missing
database is a broken deploy → 500 that says so. Input spellings: all accepted NDC
spellings resolve identically.

## 15. UI pages, rendering model, and canonical addresses

**Server-rendered by default** (SEO is a product requirement: the people this
tool exists for find it via search). Server components fetch the API directly
via `lib/api.server.ts` (`NDCRES_API_BASE ?? NDCRES_API_PROXY ?? local dev
uvicorn`, Next data-cache `revalidate` ~1h) — the `next.config.ts` rewrite
serves only incoming browser requests from the remaining client islands.

- Server pages: `/` · `/ndc/[ndc]` · `/class/[slug]` (canonical class page) ·
  `/gaps` · `/sources` · `/dossier/[ndc]` · `/compare/[a]/[b]` ·
  `/note/[a]/[b]`. Each carries `generateMetadata` (drug names in titles;
  descriptions use `verdict_language` — probabilistic by construction).
- Client islands (enumerated; everything else is server): `SearchBox`,
  `BrowseClient` (the `/browse` body — interactive search stays client behind
  a metadata-bearing server shell), `MetaFooter`, `PrintButton`,
  `app/error.tsx`.
- **Canonical scheme**: a TE-rated class's address is `/class/{slug}` — slug =
  pure function of the class key: lowercased human head (first two
  ingredients + form;route + humanized strength + TE, capped ~80 chars) +
  8-hex sha1 suffix of the full joined key. The suffix is load-bearing: keys
  collide after punctuation cleaning (`RAW:0.05%` vs `RAW:005`); the hash
  cannot. Slugs are stored nowhere (`classpage.py` computes + caches per
  (db, sweep_id) — the serving db is immutable per deploy). `/ndc/[ndc]`
  pages declare `rel=canonical` to their class page via the resolution's
  `class_ref`.
- **Sitemap policy** (`app/sitemap.ts`): the ~2,900 `/class/{slug}` URLs +
  static pages, `lastModified` = sweep run_date; `/ndc/*` package URLs are
  DELIBERATELY excluded (canonicals exist; 216k package URLs = crawl waste).
  A sitemap must never 500 — API failure degrades to the static core.
  `app/robots.ts`: allow all, disallow `/api/`, sitemap reference.
- The printable note's "Prepared" date is DATASET-RELATIVE (max sources
  fetched_at) — never wall-clock (§7.1 discipline; also hydration-safe).
- UI has no independent data logic — it renders API payloads. (No JS unit
  tests by design; behavior is pinned at the API layer, rendering verified by
  `npm run build`'s RSC compilation and deploy smoke checks. Revisit if UI
  logic grows beyond rendering.)

## 16. Deployment & weekly pipeline

- **Two Vercel projects** (docs/DEPLOY_NOTES.md is the operational record):
  the Next.js UI (zero data, zero Python; proxies `/api/*` via `NDCRES_API_PROXY`
  rewrite) and `ndcres-api` (FastAPI + bundled `web.db`, deployed from
  `apiserver/` with legacy `builds` config; `sync-assets.mjs` stages the package
  copy + artifact).
- The serving artifact `web.db` is produced by `export --web`: explicit table
  enumeration, NADAC trimmed to latest+baseline, SDUD 2 years, size-gated;
  **rollback-journal header** (WAL cannot open on a read-only filesystem) and
  served via `connect_readonly` — both pinned by tests.
- Weekly `.github/workflows/data-refresh.yml`: refresh all sources → export →
  smoke-check the golden anchor → publish `web.db` to the rolling `data` release
  → redeploy ndcres-api (job-level env gates the token). Phase 4 adds the
  history asset. CI (`ci.yml`): pytest + mypy on push/PR.

## 17. Non-goals & exclusions (each is a decision, not an accident)

- **No live pharmacy inventory**; no scraping of CVS/Walgreens/McKesson/Cardinal/
  Cencora properties (ToS + CFAA exposure).
- **No PHI, ever.** No accounts, no tracking.
- **No clinical recommendations** — prescriber-authorization framing only.
- **No credential-gated sources** (that excludes: Canada HPS API, UK SPS tool,
  ASHP as a feed — ASHP terms forbid reuse; EMA catalogue skipped as thin).
- **US-only data pipeline** (operator decision 2026-08-13): no foreign shortage
  ingestion; foreign listings may appear only as labeled external references in
  the exhibit appendix.
- **No facility-level publication** (USP/HHS/RAND norm): class/molecule level
  only; no per-facility or brittleness-map outputs.
- No signal-threshold auto-tuning against FDA-list history.

## 18. Language & legal discipline

- The disclaimer (single home: `serialize.DISCLAIMER`) accompanies every payload
  and every rendered surface.
- Absence of a shortage record renders "not on FDA shortage list" + lagging-source
  caveat. Banned framings: "available", "no shortage", "shortage confirmed"
  (outside the fda-listed verdict wording).
- Verdict wording flows only from `VERDICT_LANGUAGE`; quiet reads quiet, never
  available.
- Every explain dimension line and signal component carries its source; Phase 2
  extends this to a per-section `source` ref with outbound URL + vintage on every
  page ("legally cover our ass" — operator).
- Upstream data is preserved verbatim where quoted (including upstream typos);
  corrections happen only via the cited `special_case` mechanism.

## 20. State substitution law (`src/ndcres/statelaw.py`)

The note page's job is prescriber-facing exactness — "in most states" is 51
different laws doing the work of one sentence. This section replaces it with
the reader's actual state rule.

- **`StateRule`**: state, name, substitution (`mandatory` | `permissive` |
  `unverified`), patient_consent_required / patient_notification_required /
  patient_may_refuse (`bool | None`, None = unknown), prescriber_override
  (exact mechanism), statute_citation, statute_url, as_of (research access
  date, always rendered).
- **Curation standard**: every row verified against the STATUTE itself
  (public domain) or two agreeing citable secondary sources (Sacks et al.,
  JAMA Internal Medicine 2020, open access; CT OLR 2013-R-0071); NABP's
  license-restricted survey is never used. A row failing verification ships
  `substitution='unverified'` and the UI falls back to the generic sentence —
  never guessed. Evidence: docs/dossiers/2026-08-statelaw-research.md.
- **Serving**: `GET /api/statelaw` (no DB dependency; the table changes only
  with a code deploy). The note page reads `?state=XX` from the URL
  (stateless, shareable, printable — the no-tracking promise, §17); the
  StatePicker island does `router.replace`. Selected state + a T1/T2 verdict
  assemble the exact language (mandatory/permissive + override mechanism +
  consent/notification/refusal clauses) + "as of {date}, per {statute link}"
  + the not-legal-advice disclaimer. No state chosen → the generic sentence
  plus a picker prompt. State law does NOT surface on /ndc or /class (keeps
  the SSR cache one variant, not 51) — the note is the artifact that travels.
- **v1 limitations (deliberate)**: no biosimilar or controlled-substance
  carve-outs (the tiers themselves already exclude what federal law
  excludes); no geo auto-detection; no storage of the choice.

## 19. Invariant → test traceability

Reference grammar: `tests/<file>::<test_name>` (class names omitted; parameterized
tests referenced by base name). Multiple pins separated by ` ; `. ⚠️ OPEN rows name
the reason and owner. The crosswalk test fails on any dangling reference.

| ID | Invariant | Pinned by |
|---|---|---|
| INV-2.1 | Each 10-digit shape pads its own segment to 11 digits | tests/test_ndc.py::test_4_4_2_pads_labeler ; tests/test_ndc.py::test_5_3_2_pads_product ; tests/test_ndc.py::test_5_4_1_pads_package |
| INV-2.2 | Bare-10 input is ambiguous; candidates are listed; duplicates collapse | tests/test_ndc.py::test_bare_10_is_ambiguous_with_three_candidates ; tests/test_ndc.py::test_bare_10_duplicate_candidates_collapse ; tests/test_cli.py::test_normalize_ambiguous_lists_candidates |
| INV-2.3 | 11-digit accepted bare, hyphenated, and brief-style reconstructed | tests/test_ndc.py::test_bare_11_is_unambiguous ; tests/test_ndc.py::test_11_digit_hyphenated_hipaa_form ; tests/test_ndc.py::test_brief_style_reconstructed_hyphenation_accepted |
| INV-2.4 | as-filed → ndc11 → HIPAA round-trip is stable for all real shapes | tests/test_ndc.py::test_filed_to_ndc11_to_hipaa_is_stable ; tests/test_ndc.py::test_hipaa_rendering |
| INV-2.5 | Non-NDC input is rejected with helpful errors, never guessed | tests/test_ndc.py::test_rejects_non_ndc_strings ; tests/test_ndc.py::test_invalid_segmentation_rejected ; tests/test_ndc.py::test_two_segments_rejected ; tests/test_cli.py::test_normalize_invalid |
| INV-2.6 | Grain helpers derive ndc9/product-ndc correctly per shape | tests/test_ndc.py::test_ndc9_of ; tests/test_ndc.py::test_product_ndc_4_4 ; tests/test_ndc.py::test_product_ndc_5_3 ; tests/test_ndc.py::test_product_ndc_5_4 ; tests/test_ndc.py::test_product_ndc_rejects_garbage |
| INV-2.7 | TE subscripts partition; blank TE = not evaluated, never wildcards | tests/test_tecode.py::test_subscripted_code ; tests/test_tecode.py::test_subscripts_partition ; tests/test_tecode.py::test_blank_means_no_evaluation ; tests/test_tecode.py::test_b_codes ; tests/test_tecode.py::test_at_subscript |
| INV-2.8 | Strengths canonicalize decimal-exact on both sources; FR suffix stripped; rate never matches mass; None never matches | tests/test_strength.py::test_patch_rate_leading_dot ; tests/test_strength.py::test_menostar_microgram_unit ; tests/test_strength.py::test_fr_suffix_stripped ; tests/test_strength.py::test_anchor_patch_matches ; tests/test_strength.py::test_menostar_cross_unit_matches ; tests/test_strength.py::test_rate_never_matches_mass ; tests/test_strength.py::test_none_never_matches ; tests/test_strength.py::test_different_strengths_do_not_match |
| INV-2.9 | Form families unify cross-source patch spellings; buccal film is not a patch; unknown forms stay distinct | tests/test_formfamily.py::test_all_three_patch_spellings_map_to_patch ; tests/test_formfamily.py::test_buccal_film_is_not_a_patch ; tests/test_formfamily.py::test_cross_source_patch_agreement ; tests/test_formfamily.py::test_unknown_forms_are_distinct_not_none |
| INV-2.10 | Package parser: multiplicative nesting; wear duration only from 3.5d/7d patterns; degenerate input never crashes | tests/test_packaging.py::test_multiplicative_nesting ; tests/test_packaging.py::test_anchor_mylan_twice_weekly ; tests/test_packaging.py::test_amneal_one_day_pouch_is_not_wear_evidence ; tests/test_packaging.py::test_unparseable_text_does_not_crash |
| INV-3.1 | cp1252 product.txt survives ingestion byte-correctly | tests/test_ingest.py::test_cp1252_labeler_survives |
| INV-3.2 | All three as-filed shapes ingest; anchor fields land exactly | tests/test_ingest.py::test_all_three_shapes_ingested ; tests/test_ingest.py::test_anchor_product_fields ; tests/test_ingest.py::test_anchor_package_fields |
| INV-3.3 | Orange Book: DISCN rows kept with NULL TE; Lyllana under the FILM heading; combo ingredient sets | tests/test_ingest.py::test_discn_rows_kept_with_null_te ; tests/test_ingest.py::test_lyllana_is_ab3_under_film_heading ; tests/test_ingest.py::test_combo_ingredient_set |
| INV-3.4 | Shortage ingest: native 10-digit segmentation normalized; upstream typo preserved verbatim; duplicate package_ndc kept | tests/test_ingest.py::test_native_segmentation_normalized ; tests/test_ingest.py::test_upstream_typo_preserved_verbatim ; tests/test_ingest.py::test_duplicate_package_ndc_kept_as_two_records |
| INV-3.5 | NADAC: weekly restatements collapse on (ndc11, effective_date); quoted code lists parse | tests/test_ingest.py::test_weekly_restatements_collapse ; tests/test_ingest.py::test_quoted_explanation_code_list ; tests/test_ingest.py::test_anchor_series_present |
| INV-3.6 | SDUD aggregates states and skips suppressed rows; enforcement indexes by ndc9 with unindexed rows kept | tests/test_class_assessment.py::test_sdud_aggregates_states_and_skips_suppressed ; tests/test_class_assessment.py::test_enforcement_indexed_by_product_ndc ; tests/test_class_assessment.py::test_enforcement_without_ndc_is_kept_unindexed |
| INV-4.1 | Refresh is idempotent; upstream mutation and removal propagate (mirror semantics) | tests/test_ingest.py::test_double_refresh_is_idempotent ; tests/test_ingest.py::test_mutation_fixture_propagates_change_and_removal |
| INV-4.2 | Every ingested row carries source_run provenance | tests/test_ingest.py::test_every_row_carries_provenance |
| INV-4.3 | Menostar special-case corrects the upstream application defect, preserving the raw value, and links to N021674 | tests/test_ingest.py::test_menostar_special_case_applied ; tests/test_ingest.py::test_menostar_links_to_its_true_application |
| INV-4.4 | OB link: strength disambiguation; authorized generics share the brand row; missing applications recorded as status, never guessed | tests/test_ingest.py::test_anchor_links_by_strength ; tests/test_ingest.py::test_authorized_generic_shares_brand_row ; tests/test_ingest.py::test_missing_ob_application_recorded ; tests/test_ingest.py::test_divigel_links_via_concentration_strength |
| INV-4.5 | RxNorm: NDC→concept lands; branded generics map via SBD and normalize to SCD | tests/test_ingest.py::test_ndc_to_concept ; tests/test_ingest.py::test_branded_generic_maps_to_sbd |
| INV-5.1 | Anchor golden: T1 is exactly the AB1 eight-counts (incl. Dotti); Lyllana T3 different-te-subgroup; Mylan's own AB3 product T3; Climara group T3 different-schedule; Menostar T3 multi-reason; gels/sprays/oral T4 | tests/test_resolve_golden.py::test_tier1_is_exactly_the_ab1_eight_counts ; tests/test_resolve_golden.py::test_lyllana_is_tier3_different_subgroup ; tests/test_resolve_golden.py::test_mylan_own_ab3_product_is_tier3 ; tests/test_resolve_golden.py::test_climara_group_is_tier3_schedule_change ; tests/test_resolve_golden.py::test_menostar_is_tier3_multi_reason ; tests/test_resolve_golden.py::test_tier4_gel_spray_oral |
| INV-5.2 | Symmetry: Lyllana as seed makes the AB3 group T1 and the anchor T3; T1 is symmetric as a property | tests/test_resolve_golden.py::test_tier1_is_the_ab3_group ; tests/test_resolve_golden.py::test_original_anchor_lands_in_tier3 ; tests/test_resolve_golden.py::test_tier1_is_symmetric |
| INV-5.3 | All input spellings resolve byte-identically; bare-10 disambiguates against the DB; unknown NDC errors helpfully | tests/test_resolve_golden.py::test_all_spellings_resolve_identically ; tests/test_resolve_golden.py::test_bare10_disambiguates_against_db ; tests/test_resolve_golden.py::test_unknown_ndc_errors_helpfully |
| INV-5.4 | Tier partition holds; resolution is deterministic; seed never its own candidate | tests/test_resolve_golden.py::test_partition_no_candidate_in_two_tiers ; tests/test_resolve_golden.py::test_resolution_is_deterministic ; tests/test_resolve_golden.py::test_seed_never_its_own_candidate |
| INV-5.5 | Blank TE never forms a group (fuzzed property) | tests/test_resolve_golden.py::test_blank_te_never_groups |
| INV-5.6 | Combos never enter single-ingredient candidate sets; sample packages excluded; discontinued seeds resolve via RxNorm with candidates capped at T3 | tests/test_resolve_golden.py::test_combo_product_never_gathered ; tests/test_resolve_golden.py::test_sample_package_excluded ; tests/test_resolve_golden.py::test_alora_surfaces_as_excluded_via_rxnorm ; tests/test_resolve_golden.py::test_alora_ndc_resolves_via_rxnorm_only |
| INV-5.7 | Same product other pack is T2; same TE family other strength reads only different-strength; unknown schedule blocks across groups, never within | tests/test_resolve_golden.py::test_same_product_other_pack_is_tier2 ; tests/test_resolve_golden.py::test_same_te_family_other_strength_is_only_different_strength ; tests/test_resolve_golden.py::test_unknown_schedule_blocks_nothing_within_group ; tests/test_resolve_golden.py::test_unknown_schedule_blocks_tier_across_groups |
| INV-6.1 | Ladder rungs map exactly (84HR/168HR only; wear duration; NADAC markers; name marker; brand map; pack-count heuristic scoped to patches) | tests/test_schedule.py::test_rxnorm_scd_84hr_is_twice_weekly ; tests/test_schedule.py::test_rxnorm_scd_168hr_is_once_weekly ; tests/test_schedule.py::test_rxnorm_other_durations_are_not_mapped ; tests/test_schedule.py::test_pack_wear_duration ; tests/test_schedule.py::test_nadac_description_markers ; tests/test_schedule.py::test_pack_count_heuristic_scoped_to_patches |
| INV-6.2 | Higher rung wins; conflicts flagged but top rung decides; no evidence = unknown; every finding carries citable detail | tests/test_schedule.py::test_higher_rung_wins ; tests/test_schedule.py::test_conflict_is_flagged_but_top_rung_decides ; tests/test_schedule.py::test_no_evidence_is_unknown_not_guessed ; tests/test_schedule.py::test_every_finding_carries_citable_detail |
| INV-7.1 | Dropout fires for a vanished NDC, stays quiet for present and never-surveyed NDCs | tests/test_signals.py::test_fires_for_the_vanished_ndc ; tests/test_signals.py::test_quiet_for_a_present_ndc ; tests/test_signals.py::test_never_surveyed_reads_quiet_not_missing_data_crash |
| INV-7.2 | Drift fires cross-year at the tuned thresholds and stays quiet for flat prices | tests/test_signals.py::test_fires_cross_year_for_the_anchor ; tests/test_signals.py::test_ten_percent_rise_fires_softly ; tests/test_signals.py::test_quiet_for_flat_price |
| INV-7.3 | Shortage absence reads lagging-list language (never "available"); active fires; Resolved never fires | tests/test_signals.py::test_absence_reads_lagging_list_never_available ; tests/test_signals.py::test_synthetic_shortage_fires ; tests/test_signals.py::test_resolved_record_does_not_fire ; tests/test_ingest.py::test_no_estradiol_records_in_real_slice |
| INV-7.4 | Signal reports are wall-clock independent | tests/test_signals.py::test_report_is_wall_clock_independent |
| INV-7.5 | Stress feeds ranking: stressed equivalents rank last in tier; dropout outranks healthy but not shortage | tests/test_signals.py::test_stressed_equivalent_ranks_last_in_tier1 ; tests/test_signals.py::test_dropout_outranks_healthy_but_not_shortage |
| INV-7.6 | Class assessment: constraint verdict without any FDA listing; FDA-listed dominates; quiet reads quiet-not-available; members are the legal class; demand surge is a fingerprint | tests/test_class_assessment.py::test_estradiol_class_shows_constraint_without_fda_listing ; tests/test_class_assessment.py::test_fda_listed_dominates ; tests/test_class_assessment.py::test_quiet_class_reads_quiet_not_available ; tests/test_class_assessment.py::test_assessment_members_are_the_legal_class ; tests/test_class_assessment.py::test_demand_surge_is_a_constraint_fingerprint |
| INV-8.1 | "estradiol .05" finds the 0.05 patch family, and strength strictly narrows the ingredient's results | tests/test_search.py::test_estradiol_dot05_finds_the_patch_family ; tests/test_search.py::test_strength_actually_narrows |
| INV-8.2 | Token order never matters; mg/mcg/glued spellings are equivalent; number+unit words join into one token | tests/test_search.py::test_token_order_never_matters ; tests/test_search.py::test_unit_spellings_are_equivalent ; tests/test_search.py::test_tokenizer_joins_number_and_unit ; tests/test_search.py::test_strength_keys_mg_and_mcg_meet ; tests/test_search.py::test_bare_number_covers_both_readings ; tests/test_search.py::test_percent_becomes_prefix |
| INV-8.3 | Form words filter to the curated family; brand, labeler, and NDC-fragment tokens match their fields (hyphen-insensitive, padded shapes included) | tests/test_search.py::test_form_word_narrows_to_patches ; tests/test_search.py::test_brand_word ; tests/test_search.py::test_labeler_word_narrows ; tests/test_search.py::test_ndc_two_segment_hyphenated ; tests/test_search.py::test_ndc_bare_eight_digits_hyphen_insensitive ; tests/test_search.py::test_ndc_full_package_spelling |
| INV-8.4 | Results are product-grain, deterministic, resolvable via the representative package, and an unmatchable token yields empty | tests/test_search.py::test_product_grain_no_duplicate_products ; tests/test_search.py::test_deterministic ; tests/test_search.py::test_rep_package_is_resolvable ; tests/test_search.py::test_multi_token_miss_is_empty_not_garbage ; tests/test_search.py::test_empty_query_is_empty ; tests/test_search.py::test_unparseable_number_matches_nothing |
| INV-8.5 | Marketed outranks unmarketed at equal text score; TE codes surface on hits | tests/test_search.py::test_marketed_ranks_above_unmarketed_at_equal_text_score ; tests/test_search.py::test_te_code_surfaces |
| INV-8.6 | search_doc covers every product with correct derivations (TE, marketed, NADAC presence, representative package, RxNorm name) and carries provenance | tests/test_search.py::test_docs_exist_for_every_product ; tests/test_search.py::test_anchor_doc_derivations ; tests/test_search.py::test_docs_carry_provenance |
| INV-10.1 | The anchor estradiol class sweeps to the constraint verdict with zero FDA listings and ≥2 fingerprints | tests/test_sweep.py::test_anchor_class_reads_constraint_without_fda_listing |
| INV-10.2 | Sweep class membership equals resolve's legal class (seed+T1+T2) — one engine, zero drift | tests/test_sweep.py::test_sweep_members_equal_resolves_legal_class |
| INV-10.3 | The verdict ladder holds universally over every swept class | tests/test_sweep.py::test_verdict_ladder_holds_for_every_class |
| INV-10.4 | An fda-listed class still reports its independent fingerprint count (verdict short-circuit never zeroes it) | tests/test_sweep.py::test_fda_listed_class_still_reports_fingerprints |
| INV-10.5 | No swept member is a sample package or a discontinued-excluded product; enumeration is deterministic with the representative among the members | tests/test_sweep.py::test_no_member_is_sample_or_discontinued_excluded ; tests/test_sweep.py::test_enumeration_is_deterministic |
| INV-10.6 | Sweep history is append-only, survives refresh wipes, and round-trips the assessment | tests/test_sweep.py::test_append_only_two_runs ; tests/test_sweep.py::test_history_survives_a_refresh ; tests/test_sweep.py::test_persisted_rows_round_trip_the_assessment |
| INV-10.9 | Membership snapshots: first run is a baseline with zero delta rows; a vanished NDC's delta row carries its last-sight state (the current db no longer has the row); TE-rated members carry class keys | tests/test_membership.py::test_first_run_is_baseline_with_no_delta_rows ; tests/test_membership.py::test_vanished_row_carries_prior_state ; tests/test_membership.py::test_state_carries_class_keys_for_te_rated_members |
| INV-10.10 | Membership snapshots are same-date idempotent, refuse when nothing was ingested, and the trailing delta window copies idempotently into a fresh db | tests/test_membership.py::test_same_snapshot_date_is_idempotent ; tests/test_membership.py::test_no_ndc_ingest_refuses_loudly ; tests/test_membership.py::test_deltas_copy_into_the_main_db_within_window ; tests/test_membership.py::test_empty_history_copies_nothing |
| INV-10.7 | FDA-list snapshots record the current list dataset-relatively, dedupe same-date re-runs, and refuse when nothing was ingested | tests/test_history.py::test_snapshot_records_current_list ; tests/test_history.py::test_same_snapshot_date_dedupes ; tests/test_history.py::test_snapshot_date_is_dataset_relative ; tests/test_history.py::test_no_shortage_ingest_fails_loudly ; tests/test_history.py::test_snapshot_into_the_main_db_itself_works |
| INV-10.8 | The archive assigns fresh sweep ids (colliding runner-local ids can't overwrite), refuses missing sweeps, and refuses corrupt archives at open | tests/test_history.py::test_appends_assign_fresh_ids ; tests/test_history.py::test_missing_sweep_refuses ; tests/test_history.py::test_corrupt_archive_refuses_at_open |
| INV-11.1 | The public case study contains ONLY ingested-source URLs (allowlist over the rendered markdown) | tests/test_dossier.py::test_public_markdown_is_ingested_data_only |
| INV-11.2 | Every dossier evidence section carries its source vintage stamp | tests/test_dossier.py::test_every_section_carries_a_vintage |
| INV-11.3 | Dossier language discipline: never "shortage confirmed"; absence renders lagging-list wording; reproduction commands present; deterministic output | tests/test_dossier.py::test_language_discipline ; tests/test_dossier.py::test_absence_reads_lagging_never_available ; tests/test_dossier.py::test_deterministic |
| INV-11.4 | The exhibit pack keeps external references strictly AFTER the "NOT pipeline data" banner, with access dates, lawyer note, and 10.30 structure | tests/test_dossier.py::test_structure_and_separation ; tests/test_dossier.py::test_external_refs_carry_access_dates |
| INV-11.5 | Dossiers build for TE-rated classes, refuse unrated seeds helpfully, and the payload carries provenance + disclaimer | tests/test_dossier.py::test_builds_for_the_anchor ; tests/test_dossier.py::test_unrated_seed_fails_helpfully ; tests/test_dossier.py::test_dict_carries_provenance_and_disclaimer |
| INV-12.1 | The anchor estradiol class leads the unlisted-constraint list in the fixture universe | tests/test_gaps.py::test_estradiol_leads_the_unlisted_list |
| INV-12.2 | The partition is clean: unlisted ⇒ constraint verdict + zero FDA members; listed_but_quiet ⊆ fda_listed with zero fingerprints | tests/test_gaps.py::test_partition_is_clean |
| INV-12.3 | Gap ranking is deterministic and evidence-ordered; counts match the run summary | tests/test_gaps.py::test_ranking_is_deterministic_and_ordered ; tests/test_gaps.py::test_counts_match_the_run_summary |
| INV-12.4 | A class moves lists when FDA lists it; no sweep yields a loud, helpful error; the payload carries provenance | tests/test_gaps.py::test_fda_listed_class_moves_lists_when_listed ; tests/test_gaps.py::test_no_sweep_is_a_loud_error ; tests/test_gaps.py::test_payload_carries_provenance |
| INV-13.1 | The legacy CSV parser handles the real archived shape and fails loudly on header drift, empty snapshots; malformed dates become None | tests/test_backtest.py::test_parses_the_real_shape ; tests/test_backtest.py::test_header_drift_fails_loudly ; tests/test_backtest.py::test_empty_snapshot_fails_loudly ; tests/test_backtest.py::test_malformed_dates_become_none ; tests/test_backtest.py::test_expected_columns_are_the_pinned_legacy_set |
| INV-13.2 | Wayback snapshots store dedup-safely with normalized names | tests/test_backtest.py::test_store_dedupes_on_the_pk |
| INV-13.3 | Name→class mapping is conservative (estradiol maps to its 3+ classes incl. the anchor; unknown names map nowhere) | tests/test_backtest.py::test_estradiol_name_maps_to_te_rated_classes ; tests/test_backtest.py::test_unknown_name_maps_nowhere |
| INV-13.4 | The replay never leaks post-cutoff data (quiet before data exists; fires at the horizon; empty members = 0) | tests/test_backtest.py::test_fires_at_the_fixture_horizon ; tests/test_backtest.py::test_quiet_before_the_data_exists ; tests/test_backtest.py::test_empty_members_zero |
| INV-13.5 | The lead-time report counts unmapped listings honestly and finds the planted early-firing case | tests/test_backtest.py::test_report_over_planted_history |
| INV-14.6 | /api/class/{slug} resolves the anchor class (Dotti in T1) and 404s helpfully on unknown slugs; /api/classes covers every latest-sweep class with unique slugs | tests/test_web.py::test_class_endpoint_resolves_by_slug ; tests/test_web.py::test_unknown_slug_404s_helpfully ; tests/test_web.py::test_classes_index_covers_every_class |
| INV-14.7 | Class slugs are deterministic, unique across the fixture universe, URL-safe, capped, and punctuation-colliding keys stay distinct (hash suffix) | tests/test_classpage.py::test_deterministic ; tests/test_classpage.py::test_unique_across_fixture_universe ; tests/test_classpage.py::test_url_safe ; tests/test_classpage.py::test_long_keys_capped_but_unique ; tests/test_classpage.py::test_punctuation_only_keys_stay_distinct ; tests/test_classpage.py::test_anchor_class_addressable ; tests/test_classpage.py::test_empty_db_empty_index |
| INV-14.8 | Resolutions carry class_ref (slug + key) for TE-rated seeds; human_strength labels render canonically with RAW honestly marked | tests/test_web.py::test_resolution_carries_class_ref ; tests/test_classpage.py::test_patch_rate ; tests/test_classpage.py::test_mass_milligrams ; tests/test_classpage.py::test_raw_is_honestly_labeled |
| INV-12.5 | Corroborations are citation-only: entry shapes validated (source enum, https, ISO dates, no "confirmed" wording); a planted corroboration on every class leaves the gap report byte-identical; the payload carries them | tests/test_corroboration.py::test_entry_shapes ; tests/test_corroboration.py::test_no_duplicate_class_keys ; tests/test_corroboration.py::test_lookup_misses_cleanly ; tests/test_corroboration.py::test_corroboration_never_alters_verdict_or_rank ; tests/test_corroboration.py::test_gap_payload_carries_corroborations |
| INV-12.6 | The audit worksheet matches the gap report's ordering, is deterministic, and every row is checkable (names, labelers, OB URLs) | tests/test_corroboration.py::test_worksheet_matches_report_ordering ; tests/test_corroboration.py::test_worksheet_is_deterministic ; tests/test_corroboration.py::test_worksheet_rows_are_checkable |
| INV-14.1 | Web and CLI serve identical JSON (one serializer, JSON-native types, zero drift) | tests/test_web.py::test_web_json_matches_cli_json |
| INV-14.2 | /api/resolve returns the corrected tiers; unknown NDC → 404 with detail | tests/test_web.py::test_anchor_resolves_with_corrected_tiers ; tests/test_web.py::test_unknown_ndc_is_404_with_detail |
| INV-14.3 | /api/explain carries the Lyllana prescriber-authorization verdict; /api/signal carries components; /api/meta reports vintages | tests/test_web.py::test_lyllana_verdict ; tests/test_web.py::test_signal_components ; tests/test_web.py::test_vintages_reported |
| INV-14.4 | /api/search finds by brand and by NDC fragment (Phase 1 re-pins with the structured engine) | tests/test_web.py::test_search_by_brand ; tests/test_web.py::test_search_by_ndc_fragment |
| INV-14.5 | Class assessment reaches the web payload | tests/test_class_assessment.py::test_web_payload_carries_the_assessment |
| INV-16.1 | The serving artifact is rollback-journal (not WAL) and opens read-only/immutable; the read-only path blocks writes and fails loudly on a missing file | tests/test_export.py::test_artifact_is_rollback_journal_not_wal ; tests/test_export.py::test_readonly_open_serves_rows ; tests/test_export.py::test_immutable_open_serves_rows ; tests/test_export.py::test_readonly_blocks_writes ; tests/test_export.py::test_missing_database_fails_loudly |
| INV-16.2 | Export size gate refuses oversized artifacts and removes the oversized file | tests/test_export.py::test_size_gate_refuses_oversized_artifact |
| INV-18.1 | Explain: every dimension line cites a source; TE dimension shows the group; special-cased data names its correction | tests/test_explain.py::test_every_dimension_line_cites_a_source ; tests/test_explain.py::test_te_dimension_shows_the_group ; tests/test_explain.py::test_te_source_mentions_the_special_case |
| INV-18.2 | Explain verdicts: Dotti = direct substitute; Lyllana = requires prescriber, TE the only differing dimension | tests/test_explain.py::test_verdict_is_direct_substitute ; tests/test_explain.py::test_verdict_requires_prescriber ; tests/test_explain.py::test_te_dimension_differs_while_everything_else_matches |
| INV-7.7 | End-marketed members count as discontinued, leaving both dropout terms; still-marketed dropouts keep counting; ancient departures (>104wk) are treated like never-surveyed so ingested history depth cannot change the axis's meaning | tests/test_class_assessment.py::test_end_marketed_dropout_counts_as_discontinued_not_dropout ; tests/test_class_assessment.py::test_still_marketed_dropout_still_fires ; tests/test_class_assessment.py::test_ancient_departures_are_not_dropouts |
| INV-7.8 | Directory-exit fires only on silent RX-active exits (planted); end-marketed vanishes never fire; without two snapshots the axis is None, reads "accumulating", and never counts toward fingerprints; the payload carries the axis count | tests/test_class_assessment.py::test_fires_on_planted_silent_exits ; tests/test_class_assessment.py::test_end_marketed_vanish_never_fires ; tests/test_class_assessment.py::test_none_without_two_snapshots_and_never_counts ; tests/test_class_assessment.py::test_payload_carries_axis_count |
| INV-10.11 | Pre-5-axis archives gain the new sweep_class columns via the additive shim, with historical rows honestly NULL | tests/test_history.py::test_old_archive_gains_columns_via_shim |
| INV-16.3 | The membership window ships in the web export so the serving path computes the same directory-exit axis | tests/test_export.py::test_membership_tables_ship |
| INV-20.1 | All 51 jurisdictions present exactly once; every row format-valid (enum, https statute URL, ISO as_of, non-empty override + citation); unverified rows are the bounded exception | tests/test_statelaw.py::test_all_51_jurisdictions_present_exactly_once ; tests/test_statelaw.py::test_row_format ; tests/test_statelaw.py::test_unverified_rows_are_the_exception |
| INV-20.2 | Statute-verified goldens hold (FL mandatory + MEDICALLY NECESSARY + may-refuse; NY §6810 daw box; MA mandatory; CT cited) | tests/test_statelaw.py::test_florida_mandatory_with_medically_necessary ; tests/test_statelaw.py::test_new_york_daw_box ; tests/test_statelaw.py::test_massachusetts_mandatory ; tests/test_statelaw.py::test_connecticut_rule_present_and_cited |
| INV-20.3 | The statelaw payload carries the not-legal-advice disclaimer and the full field set; lookup normalizes and misses cleanly | tests/test_statelaw.py::test_payload_shape_and_disclaimer ; tests/test_statelaw.py::test_lookup_normalizes ; tests/test_statelaw.py::test_unknown_returns_none |
| INV-9.1 | Every ingest source and every derived table has a registry identity; refs merge live run state (url + fetched_at present after ingest) | tests/test_provenance.py::test_every_ingest_source_has_identity ; tests/test_provenance.py::test_derived_tables_have_identity_too ; tests/test_provenance.py::test_refs_merge_live_run_state |
| INV-9.2 | Orange Book / RxNav deep links build correctly and refuse garbage | tests/test_provenance.py::test_anda_deep_link ; tests/test_provenance.py::test_nda_deep_link_pads_to_six ; tests/test_provenance.py::test_rxnav_link ; tests/test_provenance.py::test_garbage_and_none_yield_none |
| INV-9.3 | Every payload (resolution/explanation/signal/search) carries a complete sources map — and the walker itself fails on stripped provenance (planted defect) | tests/test_provenance.py::test_resolution_payload ; tests/test_provenance.py::test_explanation_payload ; tests/test_provenance.py::test_signal_payload ; tests/test_provenance.py::test_search_payload ; tests/test_provenance.py::test_the_walker_actually_fails_on_stripped_provenance |
| INV-9.4 | Annotated rows deep-link their TE claim to the Orange Book application page | tests/test_provenance.py::test_anchor_row_links_to_its_orange_book_page |
| INV-18.3 | The disclaimer accompanies every serialized payload | tests/test_provenance.py::test_resolution_payload ; tests/test_provenance.py::test_the_walker_actually_fails_on_stripped_provenance |
| INV-15.1 | UI pages render API payloads without independent data logic | ⚠️ OPEN by design — no JS test rig; behavior pinned at the API layer (INV-14.x), rendering verified manually + deploy smoke; revisit if UI logic grows |

Change control: renumbering existing INV ids is forbidden (append new ones);
deleting a row requires deleting the invariant from the app or documenting the
replacement row in the same commit.
