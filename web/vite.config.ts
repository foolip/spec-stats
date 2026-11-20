import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// The site's pages are rendered on the server (src/page.ts). `npm run
// build` runs scripts/build.ts, which uses this config for the browser's
// script (src/main.ts) and then renders every page into dist/. The dev
// server renders each page on request instead, with the controller as a
// module, and serves the data file built by `python3 -m specstats build`
// (docs/site-design.md), ../build/data.json, as /data.json.
export const DATA = fileURLToPath(new URL("../build/data.json", import.meta.url));

export function readData(): string {
  try {
    return readFileSync(DATA, "utf-8");
  } catch {
    throw new Error(`${DATA} is missing: run \`python3 -m specstats build\` in the repo root first`);
  }
}

function pages(): Plugin {
  return {
    name: "spec-stats-pages",
    configureServer(server) {
      server.middlewares.use("/data.json", (_req, res) => {
        res.setHeader("Content-Type", "application/json");
        res.end(readData());
      });
      // "/", "/reviews/" and "/reviews/html/", as on the published site.
      server.middlewares.use(async (req, res, next) => {
        const path = new URL(req.url ?? "/", "http://localhost").pathname;
        if (!/^\/(?:[a-z-]+\/(?:[a-z0-9-]+\/)?)?$/.test(path)) return next();
        try {
          const { renderPage } = await server.ssrLoadModule("/src/page.ts");
          const html = renderPage(JSON.parse(readData()), {
            path: path.slice(1),
            base: "/",
            data: "data.json",
            main: "src/main.ts",
            controller: { src: "/src/controller.ts" },
            icon: readFileSync(fileURLToPath(new URL("public/favicon.svg", import.meta.url)), "utf-8"),
          });
          res.setHeader("Content-Type", "text/html");
          res.end(await server.transformIndexHtml(req.url ?? "/", html));
        } catch (e) {
          if (e instanceof Error) server.ssrFixStacktrace(e);
          next(e);
        }
      });
    },
  };
}

export default defineConfig({
  base: "./",
  appType: "custom",
  plugins: [svelte(), pages()],
  build: {
    manifest: true,
    rollupOptions: { input: "src/main.ts" },
  },
});
