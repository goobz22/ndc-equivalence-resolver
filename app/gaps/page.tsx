import type { Metadata } from "next";
import Link from "next/link";
import { GapEntry } from "@/lib/api";
import { serverApi } from "@/lib/api.server";
import { SourceTag } from "@/components/SourceTag";

export async function generateMetadata(): Promise<Metadata> {
  try {
    const report = await serverApi.gaps(1);
    const unlisted = report.totals["unlisted_constraints"];
    const listed = report.totals["fda_listed"];
    return {
      title: "The supply gap the FDA shortage list misses",
      description:
        `${unlisted} US drug classes show independent public evidence ` +
        `consistent with a supply constraint while absent from FDA's ` +
        `voluntary shortage list (which covers ${listed}). Updated weekly ` +
        `from federal price, survey, volume, and recall data.`,
    };
  } catch {
    return { title: "The supply gap the FDA shortage list misses" };
  }
}

function strengthLabel(strengthNorm: string): string {
  if (strengthNorm.startsWith("UG24H:")) return `${strengthNorm.slice(6)} mcg/24hr`;
  if (strengthNorm.startsWith("UG:")) {
    const micrograms = Number(strengthNorm.slice(3));
    if (Number.isFinite(micrograms) && micrograms >= 1000) {
      return `${micrograms / 1000} mg`;
    }
    return `${strengthNorm.slice(3)} mcg`;
  }
  if (strengthNorm.startsWith("PCT:")) return `${strengthNorm.slice(4).split(";")[0]}%`;
  if (strengthNorm.startsWith("RAW:")) return `${strengthNorm.slice(4)} (as filed)`;
  return strengthNorm || "?";
}

function FingerprintChips({ entry }: { entry: GapEntry }) {
  return (
    <span>
      {entry.drift_fired && entry.drift_pct != null ? (
        <span className="badge warn">
          price {entry.drift_pct >= 0 ? "+" : ""}
          {(entry.drift_pct * 100).toFixed(0)}%
        </span>
      ) : null}
      {entry.dropout_ratio != null &&
      entry.dropout_ratio >= 0.25 &&
      entry.surveyed_count >= 3 ? (
        <span className="badge warn">
          {entry.dropout_members}/{entry.surveyed_count} left the price survey
        </span>
      ) : null}
      {entry.volume_change_pct != null &&
      (entry.volume_change_pct <= -0.15 || entry.volume_change_pct >= 0.25) ? (
        <span className="badge warn">
          volume {entry.volume_change_pct >= 0 ? "+" : ""}
          {(entry.volume_change_pct * 100).toFixed(0)}%
        </span>
      ) : null}
      {entry.recalls > 0 ? (
        <span className="badge warn">
          {entry.recalls} recall{entry.recalls === 1 ? "" : "s"}
        </span>
      ) : null}
    </span>
  );
}

function GapTable({
  entries,
  emptyText,
}: {
  entries: GapEntry[];
  emptyText: string;
}) {
  if (entries.length === 0) {
    return <p className="tier-sub">{emptyText}</p>;
  }
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="dim-table">
        <thead>
          <tr>
            <th>drug class</th>
            <th>form;route</th>
            <th>strength</th>
            <th>TE</th>
            <th>products</th>
            <th>independent evidence</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr
              key={`${entry.ingredient_set}|${entry.df_route}|${entry.strength_norm}|${entry.te_code}`}
            >
              <td>
                <Link href={`/ndc/${entry.rep_ndc11}`}>
                  {entry.ingredient_set.toLowerCase().split("|").join(" + ")}
                </Link>
              </td>
              <td>{entry.df_route.toLowerCase()}</td>
              <td>{strengthLabel(entry.strength_norm)}</td>
              <td>{entry.te_code}</td>
              <td>{entry.member_count}</td>
              <td>
                <b>{entry.fingerprints}/4</b> <FingerprintChips entry={entry} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function GapsPage() {
  const report = await serverApi.gaps(100);
  const unlistedTotal = report.totals["unlisted_constraints"];
  const listedTotal = report.totals["fda_listed"];

  return (
    <>
      <section className="tier-section">
        <h2>The gap between the FDA shortage list and the public evidence</h2>
        <p className="lede">
          Every week this site assesses all{" "}
          {report.sweep.class_count.toLocaleString()} therapeutically-
          interchangeable drug classes in the US against four independent
          public signals: acquisition-price spikes, products vanishing from
          the federal price survey, national dispensed-volume shocks, and
          recalls. As of {report.sweep.run_date}:{" "}
          <b>
            {unlistedTotal} classes show independent evidence consistent with
            a supply constraint while appearing nowhere on FDA&apos;s
            voluntary shortage list
          </b>{" "}
          — the list covers {listedTotal}.
        </p>
        <p className="tier-sub">{report.note}</p>
        <SourceTag
          refs={report.sources}
          ids={["shortage", "nadac", "sdud", "enforcement"]}
        />
      </section>

      <section className="tier-section">
        <h2>
          Evidence-consistent constraints NOT on the FDA list ({unlistedTotal})
        </h2>
        <p className="tier-sub">
          Ranked by independent evidence strength, then breadth. Click a class
          to see its products, substitutable alternatives, and full evidence.
          Showing the top {report.unlisted_constraints.length}.
        </p>
        <GapTable
          entries={report.unlisted_constraints}
          emptyText="No unlisted constraint classes in the latest sweep."
        />
      </section>

      <section className="tier-section">
        <h2>On the FDA list ({listedTotal})</h2>
        <p className="tier-sub">
          Classes where the official list and this instrument agree there is
          a problem. Showing the top {report.fda_listed.length}.
        </p>
        <GapTable
          entries={report.fda_listed}
          emptyText="No FDA-listed classes in the latest sweep."
        />
      </section>

      <section className="tier-section">
        <h2>
          On the FDA list with zero independent fingerprints (
          {report.totals["listed_but_quiet"]})
        </h2>
        <p className="tier-sub">
          Listed shortages where none of the four independent signals fire —
          possibly resolved in practice, possibly constrained in ways these
          datasets cannot see. Shown for completeness: an honest instrument
          reports disagreement in both directions.
        </p>
        <GapTable
          entries={report.listed_but_quiet}
          emptyText="Every FDA-listed class also shows independent evidence."
        />
      </section>
    </>
  );
}
