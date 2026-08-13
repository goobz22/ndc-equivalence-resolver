// Build-time step: make api/ self-contained for Vercel's zero-config
// Python runtime. With the Next.js framework preset, `functions`
// config cannot claim api/*.py, and the Python builder bundles only the
// api/ directory itself — so the package and the serving database are
// copied in here during `npm run build`. Both copies are gitignored;
// they exist only inside builds.

import { cpSync, existsSync, statSync } from "node:fs";

if (!existsSync("data/web.db")) {
  console.error("prepare-api: data/web.db missing — run fetch-db first");
  process.exit(1);
}
cpSync("src/ndcres", "api/ndcres", { recursive: true });
cpSync("data/web.db", "api/web.db");
console.log(
  `prepare-api: bundled ndcres package + web.db (${(
    statSync("api/web.db").size / 1e6
  ).toFixed(1)}MB) into api/`,
);
