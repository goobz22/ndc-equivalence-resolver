import type { NextConfig } from "next";

// NDCRES_API_PROXY points at the ndcres-api deployment (set on the
// Vercel UI project in production; http://127.0.0.1:8600 in local dev).
// This rewrite serves INCOMING browser requests to /api/* — server
// components never use it (they fetch the base directly via
// lib/api.server.ts, which reads the same env var).
const apiBase = process.env.NDCRES_API_PROXY;

const nextConfig: NextConfig = {
  async rewrites() {
    if (!apiBase) return [];
    return [{ source: "/api/:path*", destination: `${apiBase}/api/:path*` }];
  },
};

export default nextConfig;
