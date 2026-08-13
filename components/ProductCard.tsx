import Link from "next/link";
import { AnnotatedEntry } from "@/lib/api";

export function ProductCard({
  entry,
  seedNdc,
  isSeed = false,
}: {
  entry: AnnotatedEntry;
  seedNdc?: string;
  isSeed?: boolean;
}) {
  const displayName = [entry.name, entry.name_suffix].filter(Boolean).join(" ");
  const filedNdc = entry.ndc_as_filed ?? entry.ndc11 ?? "?";
  const stress = entry.stress_score ?? 0;

  return (
    <div className={`card${isSeed ? " seed-card" : ""}`}>
      <h3>
        {entry.ndc11 ? (
          <Link href={`/ndc/${entry.ndc11}`}>{displayName || "(unnamed)"}</Link>
        ) : (
          displayName || "(unnamed)"
        )}{" "}
        <span className="sub">{filedNdc}</span>
      </h3>
      <div className="sub">{entry.labeler ?? "labeler unknown"}</div>
      <div className="row">
        {entry.te_code ? (
          <span className="badge te">TE {entry.te_code}</span>
        ) : (
          <span className="badge">no TE rating</span>
        )}
        {entry.pack_count ? (
          <span className="badge">{entry.pack_count}-count</span>
        ) : null}
        {entry.schedule ? <span className="badge">{entry.schedule}</span> : null}
        {entry.nadac_per_unit != null ? (
          <span className="badge">
            NADAC ${entry.nadac_per_unit.toFixed(2)}/unit
            {entry.pack_count
              ? ` (~$${(entry.nadac_per_unit * entry.pack_count).toFixed(2)}/carton)`
              : ""}
          </span>
        ) : (
          <span className="badge">no NADAC record</span>
        )}
        {entry.shortage_statuses.length > 0 ? (
          <span className="badge danger">
            shortage: {entry.shortage_statuses.join(", ")}
          </span>
        ) : (
          <span className="badge ok">no known shortage record</span>
        )}
        {stress > 0 ? (
          <span className={`badge ${stress >= 0.5 ? "danger" : "warn"}`}>
            supply-stress {stress.toFixed(2)}
          </span>
        ) : null}
        {!entry.marketed ? <span className="badge warn">not marketed</span> : null}
      </div>
      {entry.stress_evidence.length > 0 ? (
        <ul className="stress-evidence">
          {entry.stress_evidence.map((evidence) => (
            <li key={evidence}>{evidence}</li>
          ))}
        </ul>
      ) : null}
      {entry.reasons.length > 0 ? (
        <ul className="reason-list">
          {entry.reasons.map((reason) => (
            <li key={reason}>
              <b>{reason}</b> — {entry.reason_language[reason] ?? reason}
            </li>
          ))}
        </ul>
      ) : null}
      {seedNdc && entry.ndc11 ? (
        <div className="row">
          <Link href={`/compare/${seedNdc}/${entry.ndc11}`}>
            Why this tier?
          </Link>
          {entry.tier !== "T4" && entry.tier !== "EXCLUDED" ? (
            <Link href={`/note/${seedNdc}/${entry.ndc11}`}>
              Printable note for your prescriber
            </Link>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
