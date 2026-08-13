# Deployment architecture and findings (2026-08-13)

## The shipped architecture: two Vercel projects, one implementation

- **`ndcres-api`** (https://ndcres-api.vercel.app) — the Python FastAPI
  resolver as its own Vercel project, deployed **from `apiserver/`**
  (`cd apiserver && vercel deploy --prod`). The 156MB `web.db` artifact
  and a fresh copy of `src/ndcres` are staged next to the entrypoint by
  `apiserver/sync-assets.mjs` before each deploy and ship inside the
  function bundle. Explicit legacy `builds` config
  (`apiserver/vercel.json`) creates exactly one `@vercel/python`
  function; a catch-all route hands every path to the ASGI app.
- **`ndc-equivalence-resolver`** (the Next.js UI) — deploys from the
  repo root, bundles **zero data and zero Python**. `NDCRES_API_PROXY`
  (project env var, set to the ndcres-api URL) activates the
  `next.config.ts` rewrite that proxies `/api/*` server-side, so the
  browser only ever talks to the UI origin.
- Weekly data refresh (`.github/workflows/data-refresh.yml`) publishes
  the artifact to the rolling `data` release **and redeploys
  ndcres-api** (the database ships inside the bundle, so a redeploy is
  what picks up fresh data — needs a `VERCEL_TOKEN` repo secret). The
  UI never needs a data rebuild: every page fetches through `/api/*`
  at request time.

Local dev is unchanged: uvicorn on :8600 over the full local database +
`NDCRES_API_PROXY=http://127.0.0.1:8600 next dev` on :3100.

## Why a split project — the mixed-layout blocker

The obvious layout (Next.js at the repo root + `api/index.py`, Vercel's
own nextjs-fastapi template) is not buildable on current Vercel
(CLI 58.x, observed across six deploys and local `vercel build` repros):

- With a `functions: {"api/index.py": ...}` block, validation fails:
  *"The pattern 'api/index.py' doesn't match any Serverless Functions."*
- Without it, the Next.js preset claims the entire build and no Python
  function is created at all.
- One deployment (dpl_3m2cHhcAHm5h9iogFPPoguzP1Co1) DID build the
  function; identical configs failed ever after — a server-side builder
  change, not anything in this repo.

Do not spend more cycles permuting `vercel.json` in a mixed layout.

## The four traps on the way to the working split (each cost a deploy)

1. **Framework auto-detection is CLI-side and sticky.** With `"next"`
   anywhere in the root `package.json`, the CLI stamps
   `framework: nextjs` onto the deployment even when the local config
   AND the project settings both say `framework: null` — the build then
   dies on "No Next.js version detected". The only reliable escape is
   deploying from a directory containing no `package.json` at all
   (hence `apiserver/` as the upload root).
2. **The Python builder's entrypoint scan is top-level-only.** It looks
   for a module-level binding named `app`/`application`/`handler`; an
   `app` bound inside `try:` is invisible ("Could not find a top-level
   'app'"). `api/index.py` ends with a plain `app = _load_app()` for
   this reason.
3. **The lambda filesystem is read-only, and the serving path must be
   too.** The read-write `connect()` (mkdir + `PRAGMA journal_mode=WAL`
   + DDL) fails there with `unable to open database file`. Serving goes
   through `connect_readonly()` (`mode=ro`, `PRAGMA query_only`), with
   `NDCRES_IMMUTABLE=1` set by the entrypoint so SQLite also skips
   locking (safe: nothing can write the bundle).
4. **A WAL-flagged artifact cannot be opened from a read-only mount**
   (readers must create the `-shm` sidecar), and `connect()` creates
   databases in WAL mode with the flag persisting in the file header
   through VACUUM. `export --web` now flips the artifact to
   rollback-journal — pinned by `tests/test_export.py` (header bytes +
   ro/immutable open contracts).

## Operational notes

- The `data` release asset must be the rollback-journal export
  (post-`81ac6b7`); a WAL-flagged `web.db` will 500 every request on
  any read-only host.
- `sync-assets.mjs` prefers a local `../data/web.db`, reuses an existing
  complete copy, else fetches the release asset (streamed to `.tmp`,
  renamed only on completion — a truncated download can never ship).
- Runtime diagnostics: a broken bundle answers with a JSON 500 carrying
  the traceback (`api/index.py` fallback app); `vercel logs <url>`
  shows per-request tracebacks.
- Deployment identity lives in env vars, not `.vercel/` links:
  `VERCEL_ORG_ID=team_dCPoXF5E9H4gY3LCVhlXHm4X`,
  `VERCEL_PROJECT_ID=prj_rD2dW3XpbY8KIHxfSygB778Nxc9x` (ndcres-api);
  the repo-root `.vercel/project.json` links the UI project
  (`prj_1yVDx1WaT7IQH7pWrUEgYRNlmOEt`).

## The unused fallback (kept for the record)

If the platform had refused the split project too, the reviewed plan
was a TypeScript port of only the ~40-line pure `assign_tier` over
export-time precomputed dimensions, served by a Next Route Handler +
better-sqlite3 and kept honest by a `tier_vectors.json` golden emitted
by the Python suite. Not needed: the single Python implementation
serves everywhere.
