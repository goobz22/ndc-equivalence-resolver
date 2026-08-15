import type { MetadataRoute } from "next";

const site =
  process.env.NEXT_PUBLIC_SITE_URL ?? "https://ndc-equivalence-resolver.vercel.app";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: "/api/",
    },
    sitemap: `${site}/sitemap.xml`,
  };
}
