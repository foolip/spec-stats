// `npm run build`: the site, into dist/ (docs/site-design.md, "Loading").
//
// 1. The browser's script, src/main.ts, with vite.config.ts.
// 2. The controller, src/controller.ts, as one minified script to inline.
// 3. The page renderer, src/page.ts, for Node.
// 4. The data file, ../build/data.json, as data-<hash>.json, so a page
//    always loads the data it was rendered from.
// 5. Every page: reviews/, reviews/<repo>/, issues/ and issues/<repo>/,
//    the site's root and 404.html (copies of issues/, the default view).
//
// SITE_BASE is the site's path on its host, which every page's links start
// with: "/spec-stats/" (GitHub Pages) unless set.

import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { build } from "vite";
import { DATA, readData } from "../vite.config.ts";

const web = dirname(dirname(fileURLToPath(import.meta.url)));
const dist = join(web, "dist");
const tmp = join(web, "node_modules", ".spec-stats-build");
const siteBase = process.env.SITE_BASE ?? "/spec-stats/";

await build({ root: web, logLevel: "warn" });

await build({
  root: web,
  logLevel: "warn",
  publicDir: false,
  build: {
    outDir: tmp,
    emptyOutDir: true,
    manifest: false,
    minify: true,
    lib: { entry: "src/controller.ts", formats: ["iife"], name: "specstatsController", fileName: () => "controller.js" },
    rollupOptions: { input: "src/controller.ts" },
  },
});

await build({
  root: web,
  logLevel: "warn",
  publicDir: false,
  build: { outDir: join(tmp, "ssr"), emptyOutDir: true, manifest: false, ssr: "src/page.ts", rollupOptions: { input: "src/page.ts" } },
});

const { renderPage, paths } = (await import(pathToFileURL(join(tmp, "ssr", "page.js")).href)) as typeof import("../src/page.ts");
const controller = readFileSync(join(tmp, "controller.js"), "utf-8").trim();
const manifest = JSON.parse(readFileSync(join(dist, ".vite", "manifest.json"), "utf-8")) as Record<string, { file: string }>;
const main = manifest["src/main.ts"].file;
rmSync(join(dist, ".vite"), { recursive: true });

const dataText = readData();
const dataFile = `data-${createHash("sha256").update(dataText).digest("hex").slice(0, 10)}.json`;
writeFileSync(join(dist, dataFile), dataText);
const raw = JSON.parse(dataText);
const icon = readFileSync(join(web, "public", "favicon.svg"), "utf-8");

function write(path: string, file = join(path, "index.html")) {
  const html = renderPage(raw, { path, root: siteBase, data: dataFile, main, controller: { code: controller }, icon });
  mkdirSync(dirname(join(dist, file)), { recursive: true });
  writeFileSync(join(dist, file), html);
}

const all = paths(raw);
for (const path of all) write(path);
write("");
write(all[0], "404.html");
rmSync(tmp, { recursive: true });

console.log(`dist/: ${all.length} pages, the site's root and 404.html, from ${DATA}; controller ${(controller.length / 1024).toFixed(1)} KB`);
