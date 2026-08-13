import type { NextConfig } from "next";

// In local dev the FastAPI backend runs on :8000 (uvicorn); in
// production Vercel routes /api/* straight to the Python function, so
// the rewrite only applies when the env var is present.
const apiBase = process.env.NDCRES_API_PROXY;

const nextConfig: NextConfig = {
  async rewrites() {
    if (!apiBase) return [];
    return [{ source: "/api/:path*", destination: `${apiBase}/api/:path*` }];
  },
};

export default nextConfig;
