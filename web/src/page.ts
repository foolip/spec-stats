// Renders the site's pages on the server (docs/site-design.md, "Loading"):
// scripts/build.ts writes them into dist/, and the Vite dev server renders
// them on request (vite.config.ts). Each page is the open PRs view with the
// values for its spec and the default range, the CSS inline, and the
// controller (src/controller.ts) inline.

import { render } from "svelte/server";
import css from "./app.css?inline";
import { fromRaw, type RawData } from "./lib/data.ts";
import type { PageConfig } from "./lib/config.ts";
import { Model } from "./lib/model.svelte.ts";
import { pageTitle } from "./lib/texts.ts";
import { href, pagePath, parse, VIEWS } from "./lib/url.ts";
import Page from "./Page.svelte";

export interface PageOptions {
  /** The page's path from the site's root: "" (the root), "reviews/" or
   * "reviews/html/". */
  path: string;
  /** The site's root on its host: "/spec-stats/" (GitHub Pages), "/". */
  root: string;
  /** The data file, from the site's root. */
  data: string;
  /** The script that mounts the islands, from the site's root. */
  main: string;
  /** The controller: its code, inlined, or (in development) its URL. */
  controller: { code: string } | { src: string };
  /** The site icon's SVG (public/favicon.svg), shown in the header. */
  icon: string;
}

/** The pages to build, by path from the site's root. The site's root and
 * 404.html are copies of the first: the default view, whose controller
 * rewrites the URL. */
export function paths(raw: RawData): string[] {
  const names = raw.repos.name;
  return VIEWS.flatMap((view) => [pagePath({ view, repo: null }), ...names.map((repo) => pagePath({ view, repo }))]);
}

/** JSON for a <script> element: no "</script>" or "<!--" inside. */
function scriptJson(value: unknown): string {
  return JSON.stringify(value).replaceAll("<", "\\u003c");
}

export function renderPage(raw: RawData, o: PageOptions): string {
  const data = fromRaw(raw);
  const ctx = { repoNames: data.repos.name, from: data.from, to: data.to };
  const state = parse(o.path, "", ctx);
  const model = new Model(data, state);
  const config: PageConfig = {
    root: o.root,
    data: o.data,
    from: data.from,
    to: data.to,
    repos: data.repos.name,
    standards: data.repos.standard,
    prerendered: href(state),
  };
  // The controller runs before the footer, as it's parsed; main.ts, a
  // module, is deferred, so it runs after. As a module itself (in
  // development), the controller is deferred too, and main.ts follows it.
  const main = `<script type="module" src="${o.root}${o.main}"></script>`;
  const controller =
    "code" in o.controller
      ? `<script>${o.controller.code.replaceAll("</script", "<\\/script")}</script>`
      : `<script type="module" src="${o.controller.src}"></script>\n${main}`;
  const icon = `data:image/svg+xml,${encodeURIComponent(o.icon)}`;
  const { body } = render(Page, { props: { model, root: o.root, icon, controller } });
  const r = state.repo === null ? -1 : data.repos.name.indexOf(state.repo);
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>${pageTitle(r < 0 ? null : data.repos.standard[r])}</title>
<meta name="description" content="How WHATWG specs are maintained, from public GitHub data.">
<link rel="icon" href="${o.root}favicon.svg" type="image/svg+xml">
<link rel="expect" href="#footer" blocking="render">
<link rel="preload" href="${o.root}${o.data}" as="fetch" crossorigin>
${"code" in o.controller ? main : ""}
<style>${css}</style>
<script type="application/json" id="config">${scriptJson(config)}</script>
</head>
<body>
${body}
</body>
</html>
`;
}
