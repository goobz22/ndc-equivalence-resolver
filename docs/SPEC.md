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
- Fingerprints (independent evidence axes): class drift ≥ +10% · dropout ratio
  ≥ 0.25 with surveyed ≥ 3 · SDUD volume decline ≤ −15% OR surge ≥ +25% ·
  recalls within 730 days.
- Verdict ladder: any active FDA record → `fda-listed-shortage`; ≥2 fingerprints →
  `evidence-consistent-with-supply-constraint`; exactly 1 → `mixed-signals`;
  else → `no-independent-stress-evidence` (which reads "quiet", never "available").
- Verdict language lives ONLY in `VERDICT_LANGUAGE` (single home).

## 8. Search engine — lands with Phase 1

Contract summary (full detail in the phase): tokenized structured search over a
per-ndc9 `search_doc` table rebuilt each refresh; token classes NDC / strength /
name-form with AND semantics and order-independence; strength aliases generated
from canonical forms ("estradiol .05" ≡ ".05 estradiol" ≡ "estradiol 0.05 mg" ≡
"50 mcg estradiol"); product-grain grouped results; deterministic ranking
(word > prefix > substring; marketed first). No FTS5 dependence.

## 9. Provenance & attribution — lands with Phase 2

Contract summary: `SOURCE_REGISTRY` (single home) merges static source identity
(publisher, landing URL, license) with live `source_run` rows (vintage, sha256);
every serialized payload section carries `source: {name, url, deep_url?, vintage,
fetched_at}`; deep links where upstream schemes are stable (Orange Book
per-application, RxNav per-RXCUI, per-year CMS dataset pages); SourceTag on every
UI data block; `/sources` page; site-wide legal footer.

## 10. Market sweep & longitudinal history — lands with Phases 3–4

Contract summary: `ndcres sweep` assesses every marketed TE-rated equivalence
class (~2,894) with the SAME `class_supply_assessment` the resolve path uses
(definitional identity pinned by test); results persist append-only
(`sweep_run`/`sweep_class`, exempt from mirror wipe); weekly pipeline appends
sweeps + FDA-list snapshots (healthdata.gov fnt4-gy9k) to a durable
`ndcres-history.db` release asset with integrity guards — the longitudinal record
the FDA list doesn't keep.

## 11. Evidence dossier — lands with Phase 5

Contract summary: one `Dossier` dataset, two renderers. The PUBLIC case study is
**100% ingested data** (every section vintage-stamped; URL-allowlist pinned by
test; "Reproduce this" commands). The petition-shaped exhibit pack adds a
clearly-separated external-references appendix (labeled "externally reported —
not pipeline data") and a 21 CFR 10.30 structure; filing is the operator's
decision, never automated.

## 12. Gap report — lands with Phase 6

Contract summary: reads the LATEST sweep only (no request-time compute); three
lists — `unlisted_constraints` (headline), `fda_listed` (concordant),
`listed_but_quiet`; ranking (fingerprints, surveyed, members, drift, key);
measurement-language headline; quality gate (hand-review of top rows, root-cause
fixes only) before the page ships publicly.

## 13. Backtest methodology — lands with Phase 7

Contract summary: FDA-list history reconstructed via the ASPE-validated Wayback
method + our own forward snapshots; lead time = first FDA listing minus earliest
≥2-fingerprint date computed from data preceding it; reports median/IQR lead
time, concordance, and the **unconfirmed-positive rate** (the FDA list is not
ground truth — that is the finding); NADAC/SDUD deepened via
`refresh --nadac-years/--sdud-years`; thresholds are documented constants, never
auto-tuned against the lagging reference.

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
| `GET /api/dossier/{ndc}` | Phase 5 |
| `GET /api/gaps?limit=` | Phase 6 |

Errors: unknown/unresolvable NDC → 404 with a helpful detail message; a missing
database is a broken deploy → 500 that says so. Input spellings: all accepted NDC
spellings resolve identically.

## 15. UI pages & data dependencies

All pages are client-fetch ("use client") against `/api/*` via the typed client
`lib/api.ts` (types mirror serialize.py):
`/` (hero = §1 positioning + tier explainer) · `/browse` (search) · `/ndc/[ndc]`
(resolution + SupplyPicture) · `/compare/[a]/[b]` (explain) · `/note/[a]/[b]`
(printable prescriber note) · Phase pages: `/dossier/[ndc]`, `/gaps`, `/sources`.
UI has no independent data logic — it renders API payloads. (No JS unit tests by
design; behavior is pinned at the API layer, page rendering verified manually and
by deploy smoke checks. Revisit if UI logic ever grows beyond rendering.)

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
| INV-14.1 | Web and CLI serve identical JSON (one serializer, JSON-native types, zero drift) | tests/test_web.py::test_web_json_matches_cli_json |
| INV-14.2 | /api/resolve returns the corrected tiers; unknown NDC → 404 with detail | tests/test_web.py::test_anchor_resolves_with_corrected_tiers ; tests/test_web.py::test_unknown_ndc_is_404_with_detail |
| INV-14.3 | /api/explain carries the Lyllana prescriber-authorization verdict; /api/signal carries components; /api/meta reports vintages | tests/test_web.py::test_lyllana_verdict ; tests/test_web.py::test_signal_components ; tests/test_web.py::test_vintages_reported |
| INV-14.4 | /api/search finds by brand and by NDC fragment (Phase 1 re-pins with the structured engine) | tests/test_web.py::test_search_by_brand ; tests/test_web.py::test_search_by_ndc_fragment |
| INV-14.5 | Class assessment reaches the web payload | tests/test_class_assessment.py::test_web_payload_carries_the_assessment |
| INV-16.1 | The serving artifact is rollback-journal (not WAL) and opens read-only/immutable; the read-only path blocks writes and fails loudly on a missing file | tests/test_export.py::test_artifact_is_rollback_journal_not_wal ; tests/test_export.py::test_readonly_open_serves_rows ; tests/test_export.py::test_immutable_open_serves_rows ; tests/test_export.py::test_readonly_blocks_writes ; tests/test_export.py::test_missing_database_fails_loudly |
| INV-16.2 | Export size gate refuses oversized artifacts | ⚠️ OPEN — gate logic lives in export.py:183-189 and fires in CI, but no unit test plants an oversized input; owner: Phase 6 (export changes) adds a gate test |
| INV-18.1 | Explain: every dimension line cites a source; TE dimension shows the group; special-cased data names its correction | tests/test_explain.py::test_every_dimension_line_cites_a_source ; tests/test_explain.py::test_te_dimension_shows_the_group ; tests/test_explain.py::test_te_source_mentions_the_special_case |
| INV-18.2 | Explain verdicts: Dotti = direct substitute; Lyllana = requires prescriber, TE the only differing dimension | tests/test_explain.py::test_verdict_is_direct_substitute ; tests/test_explain.py::test_verdict_requires_prescriber ; tests/test_explain.py::test_te_dimension_differs_while_everything_else_matches |
| INV-18.3 | The disclaimer accompanies every serialized payload | ⚠️ OPEN — DISCLAIMER is attached in serialize.py for resolve/search/meta and asserted nowhere; owner: Phase 2 provenance payload-walk test asserts disclaimer + source refs on every payload |
| INV-15.1 | UI pages render API payloads without independent data logic | ⚠️ OPEN by design — no JS test rig; behavior pinned at the API layer (INV-14.x), rendering verified manually + deploy smoke; revisit if UI logic grows |

Change control: renumbering existing INV ids is forbidden (append new ones);
deleting a row requires deleting the invariant from the app or documenting the
replacement row in the same commit.
