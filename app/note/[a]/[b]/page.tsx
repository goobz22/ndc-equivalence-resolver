import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Explanation } from "@/lib/api";
import {
  ApiError,
  serverApi,
  StatelawPayload,
  StateRule,
} from "@/lib/api.server";
import { PrintButton } from "@/components/PrintButton";
import { StatePicker } from "@/components/StatePicker";

export const metadata: Metadata = {
  title: "Prescription availability note",
  description:
    "A printable, source-cited note for your pharmacist and prescriber " +
    "when your exact prescription is out of stock.",
};

async function fetchExplanation(
  a: string,
  b: string,
): Promise<Explanation | null> {
  try {
    return await serverApi.explain(decodeURIComponent(a), decodeURIComponent(b));
  } catch (problem) {
    if (problem instanceof ApiError && problem.status === 404) return null;
    throw problem;
  }
}

function preparedDate(explanation: Explanation): string {
  // Dataset-relative, never wall-clock: the note is prepared FROM data,
  // so it is honestly dated BY the data (SPEC §7.1 discipline).
  const dates = Object.values(explanation.sources ?? {})
    .map((ref) => ref.fetched_at?.slice(0, 10))
    .filter((d): d is string => Boolean(d));
  return dates.length > 0 ? dates.sort()[dates.length - 1] : "unknown";
}

// The assembled rule sentence for a direct (T1/T2) substitution — the
// exact language replaces "in most states". Wording stays
// statute-anchored and probabilistic-free: the law is citable fact.
function StateLawBlock({
  rule,
  disclaimer,
}: {
  rule: StateRule;
  disclaimer: string;
}) {
  if (rule.substitution === "unverified") return null;
  const kind =
    rule.substitution === "mandatory"
      ? "the pharmacist is generally REQUIRED to substitute an FDA-rated " +
        "equivalent (unless the prescriber has blocked substitution)"
      : "the pharmacist MAY substitute an FDA-rated equivalent";
  const clauses: string[] = [];
  if (rule.patient_consent_required === true)
    clauses.push("patient consent is required before substitution");
  if (rule.patient_notification_required === true)
    clauses.push("the patient must be notified of the substitution");
  if (rule.patient_may_refuse === true)
    clauses.push("the purchaser may refuse the substitution");
  return (
    <div className="field">
      <b>State substitution rule — {rule.name}</b>
      <p>
        Under {rule.statute_citation}, {kind}
        {clauses.length > 0 ? `; ${clauses.join("; ")}` : ""}. Prescriber
        override mechanism: {rule.prescriber_override}
      </p>
      <p style={{ fontSize: "0.8rem" }}>
        As of {rule.as_of}, per{" "}
        <a href={rule.statute_url} target="_blank" rel="noreferrer">
          {rule.statute_citation}
        </a>
        . {disclaimer}
      </p>
    </div>
  );
}

export default async function NotePage({
  params,
  searchParams,
}: {
  params: Promise<{ a: string; b: string }>;
  searchParams: Promise<{ state?: string }>;
}) {
  const { a, b } = await params;
  const { state } = await searchParams;
  const explanation = await fetchExplanation(a, b);
  if (!explanation) notFound();
  let statelaw: StatelawPayload | null = null;
  try {
    statelaw = await serverApi.statelaw();
  } catch {
    statelaw = null; // the note still renders with the generic sentence
  }
  const stateRule =
    state && statelaw
      ? (statelaw.states.find(
          (entry) => entry.state === state.trim().toUpperCase(),
        ) ?? null)
      : null;

  const current = explanation.left;
  const requested = explanation.right;
  const isDirect = explanation.verdict === "T1" || explanation.verdict === "T2";
  const dims = Object.fromEntries(
    explanation.dimensions.map((line) => [line.dimension, line]),
  );

  return (
    <>
      <div className="note-actions">
        <PrintButton label="Print this note" />
        {statelaw ? (
          <StatePicker
            states={statelaw.states.map(({ state: code, name }) => ({
              state: code,
              name,
            }))}
          />
        ) : null}
      </div>

      <div className="note-sheet">
        <h2>Prescription availability note</h2>
        <p className="sub">
          Prepared from public FDA/NLM/CMS reference data (fetched{" "}
          {preparedDate(explanation)}) via the open-source NDC Equivalence
          Resolver. For discussion with your pharmacist and prescriber — this
          is not medical advice.
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
              Orange Book three-character TE code under the same heading).{" "}
              {stateRule && stateRule.substitution !== "unverified"
                ? `Under ${stateRule.name} law the pharmacist ${
                    stateRule.substitution === "mandatory"
                      ? "is generally required to"
                      : "may"
                  } substitute directly`
                : "In most states the pharmacist may substitute directly"}
              {explanation.verdict === "T2"
                ? ", with a quantity adjustment on the prescription"
                : ""}
              . No new prescription should be needed — this note is for
              confirmation.
              {!stateRule
                ? " (Choose your state above for the exact rule.)"
                : ""}
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

        {stateRule && statelaw ? (
          <StateLawBlock rule={stateRule} disclaimer={statelaw.disclaimer} />
        ) : null}

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
              .map(
                (ref) => `${ref.name} (fetched ${ref.fetched_at?.slice(0, 10)})`,
              )
              .join(" · ")}
            {" — "}all U.S. federal public data; verification and methodology:
            ndc-equivalence-resolver.vercel.app/sources
          </p>
        </div>
      </div>
    </>
  );
}
