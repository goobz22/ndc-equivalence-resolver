import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ApiError, DossierPayload, serverApi } from "@/lib/api.server";
import { PrintButton } from "@/components/PrintButton";
import { SourceTag } from "@/components/SourceTag";
import { SupplyPicture } from "@/components/SupplyPicture";

async function fetchDossier(ndc: string): Promise<DossierPayload | null> {
  try {
    return await serverApi.dossier(decodeURIComponent(ndc));
  } catch (problem) {
    if (problem instanceof ApiError && problem.status === 404) return null;
    throw problem;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ ndc: string }>;
}): Promise<Metadata> {
  const { ndc } = await params;
  const dossier = await fetchDossier(ndc);
  if (!dossier) return { title: "Evidence dossier" };
  const ingredient = dossier.class_key.ingredient_set
    .toLowerCase()
    .split("|")
    .join(" + ");
  return {
    title: `Supply evidence dossier: ${ingredient} (TE ${dossier.class_key.te_code})`,
    description: dossier.assessment.verdict_language,
  };
}

export default async function DossierPage({
  params,
}: {
  params: Promise<{ ndc: string }>;
}) {
  const { ndc } = await params;
  const dossier = await fetchDossier(ndc);
  if (!dossier) notFound();

  const key = dossier.class_key;

  return (
    <>
      <div className="note-actions">
        <PrintButton label="Print this dossier" />
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
