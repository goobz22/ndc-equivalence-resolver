"use client";

import { use, useEffect, useState } from "react";
import { api, Resolution, TIER_TITLES, TIER_SUBTITLES } from "@/lib/api";
import { ProductCard } from "@/components/ProductCard";
import { SourceTag } from "@/components/SourceTag";
import { SupplyPicture } from "@/components/SupplyPicture";

export default function ResolvePage({
  params,
}: {
  params: Promise<{ ndc: string }>;
}) {
  const { ndc } = use(params);
  const [resolution, setResolution] = useState<Resolution | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .resolve(decodeURIComponent(ndc))
      .then(setResolution)
      .catch((problem: Error) => setError(problem.message));
  }, [ndc]);

  if (error) return <div className="error-box">{error}</div>;
  if (!resolution) return <div className="loading">Resolving…</div>;

  const seed = resolution.seed;
  const seedNdc = seed?.ndc11 ?? decodeURIComponent(ndc);

  return (
    <>
      <section className="tier-section">
        <h2>You asked about</h2>
        {seed ? <ProductCard entry={seed} isSeed /> : null}
        <SourceTag
          refs={resolution.sources}
          ids={["ndc", "orangebook", "rxnorm"]}
        />
        {resolution.class_assessment ? (
          <>
            <SupplyPicture
              assessment={resolution.class_assessment}
              refs={resolution.sources}
            />
            <p style={{ marginTop: "0.5rem" }}>
              <a href={`/dossier/${seedNdc}`}>
                Full evidence dossier for this class →
              </a>
            </p>
          </>
        ) : null}
        {resolution.notes.map((note) => (
          <div key={note} className="card">
            <span className="badge warn">{note}</span>
          </div>
        ))}
      </section>

      {(["T1", "T2", "T3", "T4"] as const).map((tier) => {
        const members = resolution.tiers[tier];
        if (!members || members.length === 0) return null;
        return (
          <section key={tier} className="tier-section">
            <h2>{TIER_TITLES[tier]}</h2>
            <p className="tier-sub">{TIER_SUBTITLES[tier]}</p>
            {tier === "T1" ? (
              <p className="tier-sub">
                <b>At the counter:</b> &quot;My prescription is out of stock —
                do you have any of these equivalents in stock or orderable?&quot;
              </p>
            ) : null}
            {members.map((entry) => (
              <ProductCard
                key={entry.ndc11 ?? entry.ndc_as_filed ?? entry.name ?? tier}
                entry={entry}
                seedNdc={seedNdc}
              />
            ))}
          </section>
        );
      })}

      {resolution.excluded.length > 0 ? (
        <section className="tier-section">
          <h2>Not current options</h2>
          <p className="tier-sub">
            Kept for transparency — discontinued products, sample packages,
            and codes no longer in the current FDA directory.
          </p>
          {resolution.excluded.map((entry) => (
            <ProductCard
              key={entry.ndc11 ?? entry.ndc_as_filed ?? entry.name ?? "x"}
              entry={entry}
            />
          ))}
        </section>
      ) : null}
    </>
  );
}
