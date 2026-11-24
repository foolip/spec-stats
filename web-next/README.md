# web-next: the site in Next.js

A clean-room implementation of the spec-stats frontend with Next.js,
written from `docs/site-design.md` and `docs/PRODUCT.md` (not from `web/`),
to compare with the Svelte site in `web/`. It shows the same two views,
open issues and open PRs ("Reviews"), for all specs or one, from the same
`build/data.json`. The decisions log in `docs/plan.md` (2026-11-24) has why
and what differs.

```
python3 -m specstats build        # from the repository root: build/data.json
cd web-next
npm ci
npm run check && npm run lint && npm test
npm run build                     # static export to out/
node scripts/serve.mjs 8080       # serves out/ as GitHub Pages would
npm run dev                       # development server
```

`SITE_BASE` sets the site's root (`/spec-stats` unless set) and
`SPECSTATS_DATA` another data file.

## Layout

- `src/lib/`: everything that isn't React, tested with `node --test`
  (`test/`): decoding the data file (`data.ts`), days and dates
  (`dates.ts`, written by hand in en-US, no `Intl`), the URL's state
  (`state.ts`), periods (`bins.ts`) and every figure a view shows
  (`model.ts`).
- `src/app/`: one page for each view and spec (`[view]/`, `[view]/[spec]/`),
  the site's root (the issues view, rewritten to `issues/`), and the 404
  page. `src/server/` reads the data file at build time.
- `src/components/`: the page (`Dashboard.tsx`, a client component) and the
  hand-written SVG charts.

## How it works

- `next build` with `output: "export"` renders every page with the default
  range's figures: header, controls, tiles, tables and the charts as empty
  boxes of their final height. `scripts/copy-data.mjs` (run before `dev`
  and `build`) copies the data file to `public/data-<hash>.json`, named by
  its contents and preloaded by every page.
- The URL is the state: `Dashboard` reads it with `useSyncExternalStore`,
  and controls write it with `history.replaceState` (a tab, with
  `pushState`), so Back and Forward work and nothing is held elsewhere.
- On a link with a query string, an inline script marks the page
  `data-pending` and the controls and sections are hidden (keeping their
  space) until the data has loaded and the URL's figures are computed.
- Every figure is computed in the browser from the data in memory, in a
  few milliseconds, so switching specs, ranges, periods or views is
  instant.
