# Deployment status and findings (2026-08-12)

## Current state

- **GitHub**: https://github.com/goobz22/ndc-equivalence-resolver — public,
  CI (pytest + mypy) green, weekly `data-refresh` workflow in place.
- **Data artifact**: the rolling `data` release carries `web.db` (156MB,
  under the export size gate), produced by `ndcres export --web` from the
  2026-08-12 live refresh of all seven sources.
- **Vercel**: project `ndc-equivalence-resolver` (team scope). The
  Next.js UI deploys and serves. The Python API function does **not**
  currently deploy — see below. The full app runs locally (uvicorn
  :8600 + `next dev` :3100 proxy).

## The Vercel Python blocker, precisely

Layout: Next.js at the repo root + `api/index.py` (FastAPI via the
`@vercel/python` runtime) — the layout of Vercel's own nextjs-fastapi
template.

Observed across six deploys and local `vercel build` repros (CLI 58.x,
server builder 58.9.5):

- With a `functions: {"api/index.py": ...}` block, the build fails at
  validation: *"The pattern 'api/index.py' defined in `functions`
  doesn't match any Serverless Functions."*
- Without the block (zero-config), the Next.js preset claims the entire
  build and **no Python function is created at all**
  (`.vercel/output/functions/` contains only Next lambdas).
- One deployment (dpl_3m2cHhcAHm5h9iogFPPoguzP1Co1, 2026-08-13 01:25 UTC)
  DID build the Python function (`out/api/index` in its file manifest;
  build log shows the Python venv + fetch-db pulling the 156MB artifact
  in 2s). The identical vercel.json failed validation on every
  subsequent attempt — consistent with a server-side builder change or
  a transient pipeline state, not with anything in this repo.

Conclusion: mixed Next.js + root-`api/` Python is not currently
buildable on this platform version. Do not spend more cycles permuting
`vercel.json`.

## The two forward paths (from the pre-implementation design review)

- **Fallback A (recommended)**: serve reads from a Next.js Route Handler
  (Node runtime + better-sqlite3) over dimensions precomputed by
  `export --web`; port ONLY the ~40-line pure `assign_tier` to TS, kept
  honest by a `tier_vectors.json` golden emitted by the Python test
  suite and replayed in vitest. No Python at serve time, single-runtime
  deploys, no platform coupling.
- **Fallback B**: keep FastAPI byte-identical and host it in a container
  (Fly.io / Railway) with the database baked into the image; Vercel
  serves the UI and rewrites `/api/*` to it (`NDCRES_API_PROXY` is
  already wired in next.config.ts). Requires choosing/creating a
  container-host account.

Build-time pieces that stay useful either way: `scripts/fetch-db.mjs`
(artifact fetch, fails loudly), `scripts/prepare-api.mjs` (self-contained
api/ bundling), the size-gated `export --web`, and the weekly
`data-refresh` workflow.
