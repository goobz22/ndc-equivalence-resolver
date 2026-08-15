import type { MetadataRoute } from "next";

const site =
  process.env.NEXT_PUBLIC_SITE_URL ?? "https://ndc-equivalence-resolver.vercel.app";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      // Feeds are crawlable freshness signals; the rest of /api/ is not
      // for crawlers. Allow must precede disallow for longest-match UAs.
      allow: ["/", "/api/feeds/"],
      disallow: "/api/",
    },
    sitemap: `${site}/sitemap.xml`,
  };
}
