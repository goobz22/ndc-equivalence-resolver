// Typed client for the ndcres FastAPI backend. The JSON shapes are
// produced by src/ndcres/serialize.py — the single serializer both the
// CLI and this UI consume.

export interface SourceRef {
  name: string;
  publisher: string;
  url: string;
  license: string;
  vintage: string | null;
  fetched_at: string | null;
  sha256: string | null;
}

export type SourceRefs = Record<string, SourceRef>;

export interface AnnotatedEntry {
  ndc11: string | null;
  ndc_as_filed: string | null;
  name: string | null;
  name_suffix: string | null;
  labeler: string | null;
  application: string | null;
  te_code: string | null;
  ob_heading: string | null;
  ob_type: string | null;
  strength: string | null;
  schedule: string | null;
  schedule_confidence: string | null;
  schedule_conflict: boolean;
  pack_count: number | null;
  pack_unit: string | null;
  marketed: boolean;
  tier: string;
  reasons: string[];
  reason_language: Record<string, string>;
  nadac_per_unit: number | null;
  nadac_effective_date: string | null;
  nadac_last_seen: string | null;
  shortage_statuses: string[];
  stress_score: number | null;
  stress_evidence: string[];
  application_url: string | null;
}

export interface ClassAssessment {
  member_count: number;
  surveyed_count: number;
  fda_listed_members: number;
  drift_pct: number | null;
  drift_fired: boolean;
  dropout_members: number;
  dropout_ratio: number | null;
  volume_change_pct: number | null;
  volume_quarter: string | null;
  recalls: number;
  fingerprints: number;
  verdict: string;
  verdict_language: string;
  lines: string[];
}

export interface ClassRef {
  slug: string;
  ingredient_set: string;
  df_route: string;
  strength_norm: string;
  te_code: string;
}

export interface Resolution {
  seed: AnnotatedEntry | null;
  class_ref: ClassRef | null;
  seed_status: string;
  notes: string[];
  class_assessment: ClassAssessment | null;
  tiers: Record<"T1" | "T2" | "T3" | "T4", AnnotatedEntry[]>;
  tier_language: Record<string, string>;
  excluded: AnnotatedEntry[];
  sources: SourceRefs;
  disclaimer: string;
}

export interface DimensionLine {
  dimension: string;
  left: string;
  right: string;
  same: boolean | null;
  source: string;
}

export interface Explanation {
  verdict: string;
  verdict_language: string;
  reasons: { code: string; language: string }[];
  dimensions: DimensionLine[];
  left: { ndc11: string | null; name: string | null };
  right: { ndc11: string | null; name: string | null };
  sources: SourceRefs;
  disclaimer: string;
}

export interface SignalComponent {
  name: string;
  fired: boolean;
  contribution: number;
  evidence: string;
}

export interface SignalReport {
  ndc11: string;
  stress_score: number;
  survey_horizon: string | null;
  components: SignalComponent[];
  note: string;
  sources: SourceRefs;
  disclaimer: string;
}

export interface SearchResult {
  ndc9: string;
  ndc11: string | null; // representative package for this product
  ndc_as_filed: string;
  name: string | null;
  name_suffix: string | null;
  generic_name: string | null;
  labeler: string | null;
  dosage_form: string | null;
  form_family: string | null;
  strength: string | null;
  te_code: string | null;
  marketed: boolean;
  package_count: number;
}

export interface CorroborationSource {
  source: string;
  url: string;
  accessed: string;
  note: string;
}

export interface GapEntry {
  ingredient_set: string;
  df_route: string;
  strength_norm: string;
  te_code: string;
  rep_ndc11: string;
  member_count: number;
  marketed_count: number;
  surveyed_count: number;
  fda_listed_members: number;
  drift_pct: number | null;
  drift_fired: boolean;
  dropout_members: number;
  dropout_ratio: number | null;
  volume_change_pct: number | null;
  volume_quarter: string | null;
  recalls: number;
  fingerprints: number;
  verdict: string;
  corroborated_by: CorroborationSource[];
}

export interface GapReport {
  sweep: {
    sweep_id: number;
    run_date: string;
    nadac_horizon: string | null;
    class_count: number;
    counts: Record<string, number>;
  };
  unlisted_constraints: GapEntry[];
  fda_listed: GapEntry[];
  listed_but_quiet: GapEntry[];
  totals: Record<string, number>;
  note: string;
  sources: SourceRefs;
  disclaimer: string;
}

export interface MetaSource {
  source: string;
  fetched_at: string;
  vintage: string | null;
  rows: number | null;
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { accept: "application/json" } });
  if (!response.ok) {
    const detail = await response
      .json()
      .then((body: { detail?: string }) => body.detail)
      .catch(() => undefined);
    throw new Error(detail ?? `request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  resolve: (ndc: string) => get<Resolution>(`/api/resolve/${encodeURIComponent(ndc)}`),
  explain: (a: string, b: string) =>
    get<Explanation>(
      `/api/explain/${encodeURIComponent(a)}/${encodeURIComponent(b)}`,
    ),
  signal: (ndc: string) => get<SignalReport>(`/api/signal/${encodeURIComponent(ndc)}`),
  search: (q: string) =>
    get<{ query: string; results: SearchResult[]; sources: SourceRefs }>(
      `/api/search?q=${encodeURIComponent(q)}`,
    ),
  gaps: (limit = 100) => get<GapReport>(`/api/gaps?limit=${limit}`),
  meta: () =>
    get<{ sources: MetaSource[]; registry: SourceRefs; disclaimer: string }>(
      "/api/meta",
    ),
};

export const TIER_TITLES: Record<string, string> = {
  T1: "Tier 1 — Direct substitutes",
  T2: "Tier 2 — Same drug, different package",
  T3: "Tier 3 — Requires prescriber authorization",
  T4: "Tier 4 — Different delivery form",
};

export const TIER_SUBTITLES: Record<string, string> = {
  T1: "Same FDA therapeutic-equivalence subgroup, strength, schedule, and package size. A pharmacist can usually substitute these without contacting your prescriber (state rules vary).",
  T2: "Therapeutically equivalent, but the prescription quantity must be adjusted.",
  T3: "Same medicine family, but NOT an automatic substitute — a prescriber must write a new or amended prescription naming the product.",
  T4: "Same molecule by a different route or form. Informational only; switching is a clinical decision.",
};
