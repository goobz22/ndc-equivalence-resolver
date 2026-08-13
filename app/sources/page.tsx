"use client";

import { useEffect, useState } from "react";
import { api, SourceRefs } from "@/lib/api";

export default function SourcesPage() {
  const [registry, setRegistry] = useState<SourceRefs | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .meta()
      .then((payload) => setRegistry(payload.registry))
      .catch((problem: Error) => setError(problem.message));
  }, []);

  if (error) return <div className="error-box">{error}</div>;
  if (!registry) return <div className="loading">Loading sources…</div>;

  return (
    <section className="tier-section">
      <h2>Data sources &amp; provenance</h2>
      <p className="tier-sub">
        Every number on this site comes from one of the public datasets below,
        fetched by the open-source pipeline and stored with the checksum and
        vintage shown. Nothing is scraped from pharmacies or private systems;
        no account or patient data is involved anywhere.
      </p>
      {Object.entries(registry).map(([key, ref]) => (
        <div className="card" key={key}>
          <h3>
            <a href={ref.url} target="_blank" rel="noreferrer">
              {ref.name}
            </a>
          </h3>
          <div className="sub">{ref.publisher}</div>
          <div className="row">
            <span className="badge">{ref.license}</span>
            {ref.fetched_at ? (
              <span className="badge">fetched {ref.fetched_at.slice(0, 10)}</span>
            ) : (
              <span className="badge warn">not yet ingested</span>
            )}
          </div>
          {ref.vintage ? (
            <p className="sub" style={{ marginTop: "0.4rem" }}>
              Vintage: {ref.vintage}
            </p>
          ) : null}
          {ref.sha256 ? (
            <p className="sub" style={{ marginTop: "0.2rem", wordBreak: "break-all" }}>
              SHA-256: {ref.sha256}
            </p>
          ) : null}
        </div>
      ))}
      <p className="tier-sub">
        The exact fetch-and-parse code for each source is public:
        {" "}
        <a
          href="https://github.com/goobz22/ndc-equivalence-resolver"
          target="_blank"
          rel="noreferrer"
        >
          github.com/goobz22/ndc-equivalence-resolver
        </a>
        {" "}
        — see <code>src/ndcres/ingest/</code> and the specification in
        {" "}<code>docs/SPEC.md</code>.
      </p>
    </section>
  );
}
