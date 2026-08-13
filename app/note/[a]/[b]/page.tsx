"use client";

import { use, useEffect, useState } from "react";
import { api, Explanation } from "@/lib/api";

function today(): string {
  return new Date().toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export default function NotePage({
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
  if (!explanation) return <div className="loading">Preparing the note…</div>;

  const current = explanation.left;
  const requested = explanation.right;
  const isDirect = explanation.verdict === "T1" || explanation.verdict === "T2";
  const dims = Object.fromEntries(
    explanation.dimensions.map((line) => [line.dimension, line]),
  );

  return (
    <>
      <div className="note-actions">
        <button onClick={() => window.print()}>Print this note</button>
      </div>

      <div className="note-sheet">
        <h2>Prescription availability note</h2>
        <p className="sub">
          Prepared {today()} from public FDA/NLM/CMS reference data via the
          open-source NDC Equivalence Resolver. For discussion with your
          pharmacist and prescriber — this is not medical advice.
        </p>

        <div className="field">
          <b>Currently prescribed (reported unavailable)</b>
          {current.name ?? "?"} — NDC {current.ndc11}
        </div>

        <div className="field">
          <b>Product the patient asks to discuss</b>
          {requested.name ?? "?"} — NDC {requested.ndc11}
        </div>

        <div className="field">
          <b>Regulatory relationship</b>
          {explanation.verdict_language}
          {explanation.reasons.length > 0 ? (
            <ul>
              {explanation.reasons.map((reason) => (
                <li key={reason.code}>{reason.language}</li>
              ))}
            </ul>
          ) : null}
        </div>

        <div className="field">
          <b>Comparison (source-cited)</b>
          <ul>
            {explanation.dimensions.map((line) => (
              <li key={line.dimension}>
                {line.dimension}: {line.left}{" "}
                {line.same === true ? "=" : line.same === false ? "vs" : "/"}{" "}
                {line.right}
              </li>
            ))}
          </ul>
        </div>

        <div className="field">
          <b>What is being requested</b>
          {isDirect ? (
            <p>
              These products are FDA-rated therapeutically equivalent (same
              Orange Book three-character TE code under the same heading). In
              most states the pharmacist may substitute directly
              {explanation.verdict === "T2"
                ? ", with a quantity adjustment on the prescription"
                : ""}
              . No new prescription should be needed — this note is for
              confirmation.
            </p>
          ) : (
            <p>
              These products are NOT rated as automatic substitutes
              {dims["application schedule"]?.same === false
                ? " (the dosing schedules differ)"
                : ""}
              {dims["strength"]?.same === false
                ? " (the strengths differ)"
                : ""}
              . If clinically appropriate, the patient asks the prescriber to
              issue a new or amended prescription naming{" "}
              <b>
                {requested.name ?? "the requested product"} (NDC{" "}
                {requested.ndc11})
              </b>
              , with quantity and directions adjusted as the prescriber deems
              fit.
            </p>
          )}
        </div>

        <div className="field">
          <b>Prescriber decision</b>
          <p>
            ☐ Approved — new/amended prescription issued&nbsp;&nbsp;&nbsp;
            ☐ Not appropriate&nbsp;&nbsp;&nbsp; ☐ Alternative:
            ______________________
          </p>
        </div>

        <div className="field">
          <b>Data provenance</b>
          <p style={{ fontSize: "0.8rem" }}>
            {Object.values(explanation.sources ?? {})
              .filter((ref) => ref.fetched_at)
              .map((ref) => `${ref.name} (fetched ${ref.fetched_at?.slice(0, 10)})`)
              .join(" · ")}
            {" — "}all U.S. federal public data; verification and methodology:
            ndc-equivalence-resolver.vercel.app/sources
          </p>
        </div>
      </div>
    </>
  );
}
