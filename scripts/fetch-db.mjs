// Build-time data artifact fetch (runs inside `npm run build` on Vercel).
//
// The serving database is NEVER committed to the repo (code only, zero
// vendored data). It is published as a GitHub Release asset by the data
// pipeline and pulled here at build time. The build FAILS LOUDLY if the
// artifact is missing or unfetchable — the one failure mode this script
// exists to prevent is silently deploying with a stale or empty database.
//
// Local dev never runs this: `next dev` proxies /api to a local uvicorn
// with your full local database (see next.config.ts).

import { createWriteStream, existsSync, mkdirSync, statSync } from "node:fs";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";

const DEFAULT_URL =
  "https://github.com/goobz22/ndc-equivalence-resolver/releases/download/data/web.db";
const url = process.env.NDCRES_DATA_URL ?? DEFAULT_URL;
const dest = "data/web.db";

if (existsSync(dest) && statSync(dest).size > 1024 * 1024) {
  console.log(`fetch-db: ${dest} already present, skipping fetch`);
  process.exit(0);
}

console.log(`fetch-db: downloading ${url}`);
const response = await fetch(url, { redirect: "follow" });
if (!response.ok || response.body === null) {
  console.error(
    `fetch-db: FAILED (${response.status} ${response.statusText}) — ` +
      "refusing to build without the data artifact. Publish data/web.db " +
      "as the 'data' release asset, or set NDCRES_DATA_URL.",
  );
  process.exit(1);
}
mkdirSync("data", { recursive: true });
await pipeline(Readable.fromWeb(response.body), createWriteStream(dest));
const size = statSync(dest).size;
if (size < 1024 * 1024) {
  console.error(`fetch-db: artifact suspiciously small (${size} bytes) — failing`);
  process.exit(1);
}
console.log(`fetch-db: wrote ${dest} (${(size / 1e6).toFixed(1)}MB)`);
