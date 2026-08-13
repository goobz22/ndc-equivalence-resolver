// Pre-deploy step for the standalone ndcres-api Vercel project.
//
// Run from apiserver/ before `vercel deploy`. Copies the two assets the
// serverless bundle needs next to the entrypoint:
//   ndcres/  — fresh copy of ../src/ndcres (gitignored; refreshed every
//              deploy so the deployed copy can never drift from src/)
//   web.db   — the serving database, taken from ../data/web.db when the
//              local export exists, else fetched from the GitHub data
//              release (same artifact the CI pipeline publishes).
//
// FAILS LOUDLY on any missing piece — the one failure mode this script
// exists to prevent is deploying an empty or stale API bundle.

import { createWriteStream, cpSync, existsSync, rmSync, statSync } from "node:fs";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";

const RELEASE_URL =
  "https://github.com/goobz22/ndc-equivalence-resolver/releases/download/data/web.db";

if (!existsSync("../src/ndcres")) {
  console.error("sync-assets: run from apiserver/ (../src/ndcres not found)");
  process.exit(1);
}
rmSync("ndcres", { recursive: true, force: true });
cpSync("../src/ndcres", "ndcres", { recursive: true });
console.log("sync-assets: copied ../src/ndcres -> ndcres/");

if (existsSync("../data/web.db") && statSync("../data/web.db").size > 1024 * 1024) {
  cpSync("../data/web.db", "web.db");
} else if (!existsSync("web.db") || statSync("web.db").size < 1024 * 1024) {
  const url = process.env.NDCRES_DATA_URL ?? RELEASE_URL;
  console.log(`sync-assets: no local export, downloading ${url}`);
  const response = await fetch(url, { redirect: "follow" });
  if (!response.ok || response.body === null) {
    console.error(`sync-assets: FAILED (${response.status}) — no database, refusing`);
    process.exit(1);
  }
  await pipeline(Readable.fromWeb(response.body), createWriteStream("web.db"));
}
const size = statSync("web.db").size;
if (size < 1024 * 1024) {
  console.error(`sync-assets: web.db suspiciously small (${size} bytes) — failing`);
  process.exit(1);
}
console.log(`sync-assets: web.db ready (${(size / 1e6).toFixed(1)}MB)`);
