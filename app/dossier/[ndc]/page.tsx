"use client";

import { use, useEffect, useState } from "react";
import { SourceRefs } from "@/lib/api";
import { SourceTag } from "@/components/SourceTag";
import { SupplyPicture } from "@/components/SupplyPicture";
import type { ClassAssessment } from "@/lib/api";

interface DossierPayload {
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
    recall_initiation: string | null;
    classification: string | null;
    status: string | null;
    reason: string | null;
  }[];
  sweep_history: {
    run_date: string;
    verdict: string;
    fingerprints: number;
  }[];
  sources: SourceRefs;
  disclaimer: string;
}

export default function DossierPage({
  params,
}: {
  params: Promise<{ ndc: string }>;
}) {
  const { ndc } = use(params);
  const [dossier, setDossier] = useState<DossierPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`/api/dossier/${encodeURIComponent(decodeURIComponent(ndc))}`, {
      headers: { accept: "application/json" },
    })
      .then(async (response) => {
        if (!response.ok) {
          const body = (await response.json().catch(() => null)) as {
            detail?: string;
          } | null;
          throw new Error(body?.detail ?? `request failed (${response.status})`);
        }
        return response.json() as Promise<DossierPayload>;
      })
      .then(setDossier)
      .catch((problem: Error) => setError(problem.message));
  }, [ndc]);

  if (error) return <div className="error-box">{error}</div>;
  if (!dossier) return <div className="loading">Assembling the evidence…</div>;

  const key = dossier.class_key;

  return (
    <>
      <div className="note-actions">
        <button onClick={() => window.print()}>Print this dossier</button>
      </div>
      <section className="tier-section">
        <h2>
          Supply evidence: {key.ingredient_set.toLowerCase()} — {key.df_route}{" "}
          — {key.strength_norm || "?"} — TE {key.te_code}
        </h2>
        <p className="tier-sub">
          Every number on this page comes from data ingested into the
          open-source resolver from public federal datasets, each stamped
          with its fetch date. Full price history is available via the CLI
          (`ndcres dossier {dossier.rep_ndc11}`).
        </p>

        <SupplyPicture assessment={dossier.assessment} refs={dossier.sources} />

        <h3>The class</h3>
        <div style={{ overflowX: "auto" }}>
          <table className="dim-table">
            <thead>
              <tr>
                <th>NDC</th>
                <th>product</th>
                <th>labeler</th>
                <th>application</th>
                <th>TE</th>
                <th>marketed</th>
              </tr>
            </thead>
            <tbody>
              {dossier.members.map((member) => (
                <tr key={member.ndc11}>
                  <td>{member.ndc_as_filed ?? member.ndc11}</td>
                  <td>{member.name ?? "?"}</td>
                  <td>{member.labeler ?? "?"}</td>
                  <td>{member.application ?? "?"}</td>
                  <td>{member.te_code ?? "?"}</td>
                  <td>{member.marketed ? "yes" : "no"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <SourceTag refs={dossier.sources} ids={["ndc", "orangebook"]} />

        <h3>FDA shortage list</h3>
        {dossier.fda_active.length > 0 ? (
          <ul>
            {dossier.fda_active.map((row) => (
              <li key={`${row.ndc11}-${row.status}`}>
                {row.ndc11}: {row.status} (posted {row.initial_posting},
                updated {row.update_date})
              </li>
            ))}
          </ul>
        ) : (
          <p className="tier-sub">
            <b>
              No entry for any of the {dossier.assessment.member_count} class
              members.
            </b>{" "}
            The list is manufacturer-self-reported and lagging — absence is
            not availability.
          </p>
        )}
        <SourceTag refs={dossier.sources} ids={["shortage"]} />

        <h3>Dispensed volume (Medicaid, national)</h3>
        <ul>
          {dossier.sdud_trend.map((row) => (
            <li key={`${row.year}Q${row.quarter}`}>
              {row.year}Q{row.quarter}: {Math.round(row.units).toLocaleString()}{" "}
              units
            </li>
          ))}
        </ul>
        <SourceTag refs={dossier.sources} ids={["sdud"]} />

        {dossier.sweep_history.length > 0 ? (
          <>
            <h3>Verdict across weekly sweeps</h3>
            <ul>
              {dossier.sweep_history.map((row, index) => (
                <li key={`${row.run_date}-${index}`}>
                  {row.run_date}: {row.verdict} ({row.fingerprints}{" "}
                  fingerprints)
                </li>
              ))}
            </ul>
          </>
        ) : null}

        <p className="disclaimer">{dossier.disclaimer}</p>
      </section>
    </>
  );
}
