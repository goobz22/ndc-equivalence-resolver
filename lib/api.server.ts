// Server-side API client — for server components only (do not import
// from "use client" files). Client components keep using lib/api.ts,
// whose relative fetches ride the next.config.ts rewrite; server
// components have no origin, so this helper targets the API base
// directly: NDCRES_API_BASE if set, else NDCRES_API_PROXY (already set
// in production on the UI project), else the local dev uvicorn.

import {
  ClassAssessment,
  Explanation,
  GapReport,
  Resolution,
  SourceRefs,
} from "@/lib/api";

const base =
  process.env.NDCRES_API_BASE ??
  process.env.NDCRES_API_PROXY ??
  "http://127.0.0.1:8600";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    detail: string,
  ) {
    super(detail);
  }
}

export async function serverGet<T>(path: string, revalidate = 3600): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    headers: { accept: "application/json" },
    next: { revalidate },
  });
  if (!response.ok) {
    const detail = await response
      .json()
      .then((body: { detail?: string }) => body.detail)
      .catch(() => undefined);
    throw new ApiError(
      response.status,
      detail ?? `API request failed (${response.status}) — is the API running?`,
    );
  }
  return response.json() as Promise<T>;
}

export interface ClassIndexEntry {
  slug: string;
  ingredient_set: string;
  df_route: string;
  strength_norm: string;
  te_code: string;
  rep_ndc11: string;
  verdict: string;
}

export interface ClassPayload {
  slug: string;
  class: {
    ingredient_set: string;
    df_route: string;
    strength_norm: string;
    te_code: string;
    rep_ndc11: string;
    member_count: number;
    marketed_count: number;
    fingerprints: number;
    verdict: string;
  };
  resolution: Resolution;
  sources: SourceRefs;
  disclaimer: string;
}

export interface DossierPayload {
  class_key: {
    ingredient_set: string;
    df_route: string;
    strength_norm: string;
    te_code: string;
  };
  rep_ndc11: string;
  members: {
    ndc11: string;
    ndc_as_filed: string | null;
    name: string | null;
    labeler: string | null;
    application: string | null;
    te_code: string | null;
    marketed: boolean;
    pack_count: number | null;
  }[];
  assessment: ClassAssessment;
  fda_active: {
    ndc11: string;
    status: string | null;
    initial_posting: string | null;
    update_date: string | null;
  }[];
  nadac_series: Record<
    string,
    { effective_date: string; price: number; as_of_last: string | null }[]
  >;
  sdud_trend: { year: number; quarter: number; units: number }[];
  recalls: {
    ndc9: string | null;
    recall_initiation: string | null;
    classification: string | null;
    status: string | null;
    reason: string | null;
  }[];
  sweep_history: { run_date: string; verdict: string; fingerprints: number }[];
  sources: SourceRefs;
  disclaimer: string;
}

export interface MetaPayload {
  sources: { source: string; fetched_at: string; vintage: string | null }[];
  registry: SourceRefs;
  disclaimer: string;
}

export const serverApi = {
  resolve: (ndc: string) =>
    serverGet<Resolution>(`/api/resolve/${encodeURIComponent(ndc)}`),
  explain: (a: string, b: string) =>
    serverGet<Explanation>(
      `/api/explain/${encodeURIComponent(a)}/${encodeURIComponent(b)}`,
    ),
  gaps: (limit = 100) => serverGet<GapReport>(`/api/gaps?limit=${limit}`),
  dossier: (ndc: string) =>
    serverGet<DossierPayload>(`/api/dossier/${encodeURIComponent(ndc)}`),
  classBySlug: (slug: string) =>
    serverGet<ClassPayload>(`/api/class/${encodeURIComponent(slug)}`),
  classes: () =>
    serverGet<{
      sweep: { sweep_id: number; run_date: string };
      count: number;
      classes: ClassIndexEntry[];
    }>("/api/classes", 86400),
  meta: () => serverGet<MetaPayload>("/api/meta"),
};
