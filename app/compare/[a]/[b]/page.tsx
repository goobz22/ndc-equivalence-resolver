"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { api, Explanation } from "@/lib/api";
import { SourceTag } from "@/components/SourceTag";

const VERDICT_CLASS: Record<string, string> = {
  T1: "t1",
  T2: "t2",
  T3: "t3",
  T4: "t4",
  EXCLUDED: "excluded",
};

export default function ComparePage({
  params,
}: {
  params: Promise<{ a: string; b: string }>;
}) {
  const { a, b } = use(params);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .explain(decodeURIComponent(a), decodeURIComponent(b))
      .then(setExplanation)
      .catch((problem: Error) => setError(problem.message));
  }, [a, b]);

  if (error) return <div className="error-box">{error}</div>;
  if (!explanation) return <div className="loading">Comparing…</div>;

  return (
    <>
      <section className="tier-section">
        <h2>
          {explanation.left.name ?? explanation.left.ndc11} vs{" "}
          {explanation.right.name ?? explanation.right.ndc11}
        </h2>
        <p className="tier-sub">
          Every row cites the public dataset it came from.
        </p>
        <table className="dim-table">
          <thead>
            <tr>
              <th>dimension</th>
              <th>{explanation.left.name ?? "A"}</th>
              <th>{explanation.right.name ?? "B"}</th>
            </tr>
          </thead>
          <tbody>
            {explanation.dimensions.map((line) => (
              <tr
                key={line.dimension}
                className={line.same === false ? "differs" : ""}
              >
                <td>
                  {line.same === false ? "≠ " : line.same === true ? "= " : "? "}
                  {line.dimension}
                  <div className="src">{line.source}</div>
                </td>
                <td>{line.left}</td>
                <td>{line.right}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className={`verdict ${VERDICT_CLASS[explanation.verdict] ?? ""}`}>
          <b>{explanation.verdict_language}</b>
          {explanation.reasons.map((reason) => (
            <p key={reason.code} style={{ marginBottom: 0 }}>
              <b>{reason.code}:</b> {reason.language}
            </p>
          ))}
        </div>

        {explanation.verdict !== "T4" && explanation.verdict !== "EXCLUDED" ? (
          <p>
            <Link href={`/note/${a}/${b}`}>
              Print a note to hand your prescriber →
            </Link>
          </p>
        ) : null}
        <SourceTag
          refs={explanation.sources}
          ids={["ndc", "orangebook", "rxnorm", "nadac", "shortage"]}
        />
      </section>
    </>
  );
}
