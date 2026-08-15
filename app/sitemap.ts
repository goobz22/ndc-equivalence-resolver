import type { MetadataRoute } from "next";
import { serverApi } from "@/lib/api.server";

// One sitemap file: ~2,900 class URLs + the static pages, far under the
// 50k-URL limit. /ndc/* package URLs are DELIBERATELY excluded — their
// pages canonicalize to /class/{slug}, and 216k package URLs would be
// crawl waste. Refreshes daily (revalidate on the /api/classes fetch).

const site =
  process.env.NEXT_PUBLIC_SITE_URL ?? "https://ndc-equivalence-resolver.vercel.app";

export const revalidate = 86400;

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const staticPages: MetadataRoute.Sitemap = [
    { url: `${site}/`, changeFrequency: "weekly", priority: 1 },
    { url: `${site}/gaps`, changeFrequency: "weekly", priority: 0.9 },
    { url: `${site}/browse`, changeFrequency: "weekly", priority: 0.6 },
    { url: `${site}/sources`, changeFrequency: "monthly", priority: 0.4 },
  ];
  try {
    const index = await serverApi.classes();
    const lastModified = new Date(`${index.sweep.run_date}T00:00:00Z`);
    return [
      ...staticPages,
      ...index.classes.map((entry) => ({
        url: `${site}/class/${entry.slug}`,
        lastModified,
        changeFrequency: "weekly" as const,
        priority: entry.verdict === "evidence-consistent-with-supply-constraint" ? 0.8 : 0.5,
      })),
    ];
  } catch {
    // A sitemap must never 500 the site — serve the static core.
    return staticPages;
  }
}
