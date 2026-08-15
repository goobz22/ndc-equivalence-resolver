import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ApiError, ClassPayload, serverApi } from "@/lib/api.server";
import { ResolutionView } from "@/components/ResolutionView";

// Human strength rendering is duplicated server-side in
// src/ndcres/classpage.py (the single Python home); this mirrors it for
// display only.
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

async function fetchClass(slug: string): Promise<ClassPayload | null> {
  try {
    return await serverApi.classBySlug(slug);
  } catch (problem) {
    if (problem instanceof ApiError && problem.status === 404) return null;
    throw problem;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const payload = await fetchClass(slug);
  if (!payload) return { title: "Drug class" };
  const info = payload.class;
  const ingredient = info.ingredient_set.toLowerCase().split("|").join(" + ");
  return {
    title: `${ingredient} ${strengthLabel(info.strength_norm)} (${info.df_route.toLowerCase()}, TE ${info.te_code}) — interchangeable products & supply evidence`,
    description:
      payload.resolution.class_assessment?.verdict_language ??
      `All FDA-rated interchangeable products for ${ingredient}, with public supply evidence.`,
    alternates: { canonical: `/class/${slug}` },
  };
}

export default async function ClassPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const payload = await fetchClass(slug);
  if (!payload) notFound();
  const info = payload.class;
  const ingredient = info.ingredient_set.toLowerCase().split("|").join(" + ");

  return (
    <>
      <section className="tier-section">
        <h2>
          {ingredient} — {strengthLabel(info.strength_norm)} —{" "}
          {info.df_route.toLowerCase()} — TE {info.te_code}
        </h2>
        <p className="tier-sub">
          One therapeutic-equivalence class: {info.member_count} package
          {info.member_count === 1 ? "" : "s"} across manufacturers, FDA-rated
          interchangeable with each other. The resolution below is seeded from
          a representative package; every member gets the same class verdict.
        </p>
      </section>
      <ResolutionView
        resolution={payload.resolution}
        seedNdc={info.rep_ndc11}
      />
    </>
  );
}
