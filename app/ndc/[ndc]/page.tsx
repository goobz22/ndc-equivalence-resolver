import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Resolution } from "@/lib/api";
import { ApiError, serverApi } from "@/lib/api.server";
import { ResolutionView } from "@/components/ResolutionView";

async function fetchResolution(ndc: string): Promise<Resolution | null> {
  try {
    return await serverApi.resolve(decodeURIComponent(ndc));
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
  const resolution = await fetchResolution(ndc);
  if (!resolution?.seed) return { title: "NDC lookup" };
  const seed = resolution.seed;
  const name = [seed.name, seed.name_suffix].filter(Boolean).join(" ");
  const display = name || "this product";
  return {
    title: `${display} (${seed.ndc_as_filed ?? decodeURIComponent(ndc)}) — equivalents & supply evidence`,
    description:
      resolution.class_assessment?.verdict_language ??
      `Substitutable alternatives and public supply evidence for ${display}.`,
    alternates: resolution.class_ref
      ? { canonical: `/class/${resolution.class_ref.slug}` }
      : undefined,
  };
}

export default async function ResolvePage({
  params,
}: {
  params: Promise<{ ndc: string }>;
}) {
  const { ndc } = await params;
  const resolution = await fetchResolution(ndc);
  if (!resolution) notFound();
  const seedNdc = resolution.seed?.ndc11 ?? decodeURIComponent(ndc);
  return <ResolutionView resolution={resolution} seedNdc={seedNdc} />;
}
