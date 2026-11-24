// Copies the published data file into public/ as data-<hash>.json, named by
// its contents (the same hash src/server/data.ts computes), and removes
// copies of earlier builds.

import { createHash } from "node:crypto";
import { readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";

const file = process.env.SPECSTATS_DATA ?? path.join(process.cwd(), "..", "build", "data.json");
const text = readFileSync(file, "utf8");
const hash = createHash("sha256").update(text).digest("hex").slice(0, 12);
const name = `data-${hash}.json`;
for (const f of readdirSync("public")) {
  if (/^data-[0-9a-f]+\.json$/.test(f) && f !== name) rmSync(path.join("public", f));
}
writeFileSync(path.join("public", name), text);
console.log(`public/${name}`);
