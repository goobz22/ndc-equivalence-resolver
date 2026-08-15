import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Explanation } from "@/lib/api";
import { ApiError, serverApi } from "@/lib/api.server";
import { SourceTag } from "@/components/SourceTag";

const VERDICT_CLASS: Record<string, string> = {
  T1: "t1",
  T2: "t2",
  T3: "t3",
  T4: "t4",
  EXCLUDED: "excluded",
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

export async function generateMetadata({
  params,
}: {
  params: Promise<{ a: string; b: string }>;
}): Promise<Metadata> {
  const { a, b } = await params;
  const explanation = await fetchExplanation(a, b);
  if (!explanation) return { title: "Compare products" };
  const left = explanation.left.name ?? explanation.left.ndc11 ?? "A";
  const right = explanation.right.name ?? explanation.right.ndc11 ?? "B";
  return {
    title: `${left} vs ${right} — are they interchangeable?`,
    description: explanation.verdict_language,
  };
}

export default async function ComparePage({
  params,
}: {
  params: Promise<{ a: string; b: string }>;
}) {
  const { a, b } = await params;
  const explanation = await fetchExplanation(a, b);
  if (!explanation) notFound();

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
