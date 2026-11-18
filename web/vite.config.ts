import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// The data file is built by `python3 -m specstats build` (docs/site-design.md)
// into ../build/data.json. The dev server serves it as /data.json, and a
// production build copies it next to index.html.
const DATA = fileURLToPath(new URL("../build/data.json", import.meta.url));

function readData(): string {
  try {
    return readFileSync(DATA, "utf-8");
  } catch {
    throw new Error(`${DATA} is missing: run \`python3 -m specstats build\` in the repo root first`);
  }
}

function data(): Plugin {
  return {
    name: "spec-stats-data",
    configureServer(server) {
      server.middlewares.use("/data.json", (_req, res) => {
        res.setHeader("Content-Type", "application/json");
        res.end(readData());
      });
    },
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "data.json", source: readData() });
    },
  };
}

export default defineConfig({
  base: "./",
  plugins: [svelte(), data()],
});
