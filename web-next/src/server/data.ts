// Reads the published data file at build time. `python3 -m specstats build`
// writes it; SPECSTATS_DATA names another file.

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fromRaw, type Data, type RawData } from "@/lib/data.ts";

const FILE = process.env.SPECSTATS_DATA ?? path.join(process.cwd(), "..", "build", "data.json");

let cached: { text: string; raw: RawData; data: Data; hash: string } | undefined;

export function loadData() {
  if (!cached) {
    const text = readFileSync(FILE, "utf8");
    const raw = JSON.parse(text) as RawData;
    cached = { text, raw, data: fromRaw(raw), hash: createHash("sha256").update(text).digest("hex").slice(0, 12) };
  }
  return cached;
}

export const BASE = process.env.NEXT_PUBLIC_SITE_BASE ?? "";

/** The data file's URL: named by its contents, so a page always gets the data it was rendered from. */
export function dataUrl(): string {
  return `${BASE}/data-${loadData().hash}.json`;
}
