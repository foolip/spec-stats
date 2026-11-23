# Site design

How the dashboards will be built from the collected data: what a build
step publishes, what the browser holds, and how time is represented.
Nothing here is built yet. The project is still collecting data
(`docs/plan.md`); this records the design agreed on 2026-11-18 so the
dashboard work starts from it. Decisions and their reasons are in the
decisions log.

## Shape

```
data/github/ ── build (Python) ───▶ build/data.json ──▶ web app (browser)
   raw, both tiers                  items, events,        compute every
                                    users + meta          metric in memory
```

- **Raw:** `data/github/`, as fetched (`docs/extraction.md`).
- **Build:** one Python step (standard library only) reads the raw files
  and writes a few small published tables. Every rule about what the raw
  data means lives here: which raw events count, how an item's state is
  worked out, what's left out, where the timeline starts.
- **Web app:** Svelte, built with Vite into static pages, one for each
  view and spec, prerendered with the data ("Frontend", below). It reads
  only the published tables and computes every metric from them, at
  build time for each page's default view and in the browser for the
  rest.

The pattern follows cosh (pages read only small published files, every
page says what dates its data covers), but where cosh publishes a summary
file per page, spec-stats publishes one set of tables that every page
reads, so a new metric is a new computation, not a new file.

## One timeline

Everything on the site covers one window: from `updated_since` in
`config/fetch.json` (2022-01-01) to the end of the last full UTC day the
data covers. No figure is shown for any day before it, even where the raw
data could give one.

- **The detail tiers stay at build time.** Items stored as their row only
  (`docs/extraction.md`, "Row-only items") are closed and were last
  updated before the window, so none is open in it and none has an
  event in it. The build skips them; they serve `check` and
  completeness only. Every item the published tables hold has its
  details, and the pages can't tell the difference and don't need to.
- **Opening state.** Items already open when the window starts ~~get a
  synthetic `_carried_in` event dated the window's first day~~ have a
  `created` before the window and no close before it (since 2026-11-23,
  when the events table went: an item is open from its creation to its
  last close). No event dated before the window is published.
- **Item dates may be older than the window.** An item's `created` is its
  real creation date, so the age of a backlog item on a day in the window
  is right. That is an attribute of an item in the window, not a figure
  for a day before it.
- **Durations anchor on their start.** Time to first response, time to
  merge and the like are attributed to the day the clock started, and
  durations that started before the window are left out.
- **Moving `updated_since`** moves the whole site's timeline, and nothing
  else changes.
- **Where events and an item disagree** (whatwg/fullscreen #220, closed
  with no `closed` event), the build decides once, for example by falling
  back to the item's `closed_at`, and `check` keeps reporting it.

## First version: open PRs and issues

The first page is the number of open PRs over time, per spec; the second
(since 2026-11-21) the same for issues. The build publishes only what
those need, and the tables grow a column or an event type at
a time as later metrics need them:

- **repos**, one row per standard: `name` (`html`, the repo's `name` in
  GitHub's API, and the spec's subdomain) and `standard` (`HTML`, the
  standard's `name` in `config/db.json`, as is: no "Standard" added), so
  pages show HTML rather than html. In the order pages list specs (since
  2026-11-22): by `standard`, with "Web Foo" sorted as WebFoo, so Web IDL
  comes between WebHID and WebNFC; pages don't sort specs themselves.
- **items**, PRs and issues (issues since 2026-11-21), one row each, and
  since 2026-11-23 nothing else: no events table.
  - repo, and number (for links and for checking a count against
    GitHub);
  - `kind`: 0 for an issue, 1 for a PR not merged in the window, 2 for a
    PR merged in it (since 2026-11-23; was `is_pr`, 1 or 0, with merges
    as `merged` events);
  - `created`: the day of `created_at`, counted from `meta.from`, so
    negative for an item opened before the window;
  - `closed`: for an item closed at the end of the window, the day of
    its last close, as days after `created`; null for an item open at
    the end. A merged PR can't be reopened, so its last close is its
    merge (the build checks, and closes it at its merge if not);
  - `later_in_day`: 1 if the last close was at a later time of day (UTC)
    than the creation, else 0. The time open in whole days, rounded up,
    is `closed + later_in_day`, so a limit in whole days (the charts'
    1, 7, 10 and 90) counts each item as the exact time would. It
    replaced `hours_to_merge` and `hours_to_close` on 2026-11-23: every
    band is a whole number of days.
- **An item is open from its creation to its last close**, as GitHub
  search sees it (since 2026-11-23): open at the end of day D if
  `created:<=D (is:open OR closed:>D)`, written with D's last second in
  UTC. Closes followed by a reopen are ignored, and every chart follows
  the same rule, so the open count, the items opened and the items
  closed agree, and any count can be checked against a search. Drafts
  are open PRs, as in `is:pr is:open`. An item is in the file if it was
  open on any day of the window by this rule.
  - On 2026-11-23's data this counts an item as open while it was
    actually closed, between a close and a later reopen, on at most 11
    issues (of about 3,100 open) and 2 PRs (of about 320) on any day,
    and never undercounts. The last day's count is exact.
  - Of 216 reopens in the window, 168 came within a day of the close
    (90 of the PRs' 102 within 10 minutes, as when a PR is closed and
    reopened to rerun CI), where counting the item as open throughout
    is about right. The rest reopen items closed for weeks to years
    (whatwg/html#8173 after 3.5 years), which then count as open all
    that time, and whose time to close runs to their new last close.
  - Rules that hid short closes and short reopens, with the rest as
    separate spans, were measured and rejected: no search could check
    them.
- **meta**: the window.

**Laid out to compress well** (since 2026-11-20): `items.number` and
`items.created` are differences from the previous item of the same repo
(the first of a repo's items holds its own value); items are written by
repo and number, so both are small. The loader (`fromRaw` in
`web/src/lib/data.ts`) turns them back into values, and `closed` into a
day of the window (Infinity while open) and the time open in days (NaN
while open). Views rely on no order of items (the order of `repos` is
the one the pages show); the web tests run each view on the same data
with its items shuffled to check. `build.expand` does the same decoding
in Python.

Sizes, gzipped: on 2026-11-20 the layout took the file from 43.9 KB to
21.5 KB, and whole hours to merge to 17.7 KB. Issues (2026-11-21) took
it to 43 KB and PRs' time to close (2026-11-22) to about 48 KB. One row
per item (2026-11-23) took it to 23.6 KB (150 KB uncompressed): no
draft events (1 KB), whole days with `later_in_day` in place of both
hours columns (16 KB), and no events table (8 KB). A single timeline of
items opened and closed each day, with item indexes, was measured and
came out no smaller gzipped than the events it would replace: indexes
compress worse than small day gaps.

`python3 -m specstats build` (`specstats/build.py`) writes it to
`build/data.json`, which isn't committed: whatever deploys the site runs
the build. Days are UTC days from `meta.from`, day 0. The
window ends on the last full UTC day before the newest time any repo's
`state.json` shows it was listed at: the newest `updated_at` seen
(`items.cursor`) or the last reconcile's start (`items.rows`). Every run
lists every repo, so that's when the data was last complete; if fetching
stops, the window stops with it. Changes after the window's end are
ignored: an item closed after it is open. A repo whose listings aren't
done, or with nothing stored (whatwg/nfc), is left out. An item whose
events disagree with its own state follows its state: a `closed` at its
`closed_at` (17 items on 2026-11-23), or a `reopened` at its
`updated_at`.

On 2026-11-23 it held 26 repos, 3,758 PRs (2,647 merged in the window)
and 6,738 issues. Each repo's open items on the last day equal its
stored open items, less those created after it, plus those closed after
it.

No users, labels or other lookups yet.

## Published tables

A star schema: one table of facts (events) and tables describing the
things they refer to (items, users, repos). This is the plan for later
metrics; since 2026-11-23 the file has no events table, as the first
views need only one row per item ("First version", above). Events come
back when a metric needs them.

- **items**, one row per issue or PR: repo, number, is_pr, author,
  created, and attributes worked out at build time (size, whether a PR
  is normative or has a WPT PR, first response, …), null where unknown.
- **events**, one row per thing that happened to an item in the window:
  UTC day, item, actor, event, and flags such as self or bot. The names
  are GitHub's: `event` as in `events.json` and the timeline API, whose
  values GitHub calls issue event types. Comments and reviews come from
  their own files but take the timeline's names, `commented` and
  `reviewed`. Event types GitHub doesn't have start with `_`: `_created`
  (from the item's `created_at`) and `_carried_in` (ours). Event types:
  - lifecycle: `_carried_in`, `_created`, `closed`, `reopened`, `merged`;
  - draft: `_carried_in_as_draft`, `_created_as_draft`,
    `convert_to_draft`, `ready_for_review`;
  - detail: `commented`, `reviewed` (with its state), `review_requested`,
    `labeled`, `unlabeled`, …
- **users**, one row per GitHub account that acts, bots included (GitHub's
  term, as in the raw data): login, and later organization and bot
  status, when ground rule 3's question about per-person figures is
  settled. Until then pages show no per-person figures.
- **repos**, one row per standard in `config/db.json`: `name` and
  `standard`, as above; later perhaps its workstream.

Alongside the tables, a **meta** object describes the data as a whole:
the window, `{"from": "2022-01-01", "to": "…"}`, read from each repo's
`state.json` in the same run as the tables, so the dates a page shows
can't disagree with its figures. Each page shows the window under its
title. It's not a table: nothing refers to it.

Each table is stored by column: an object of arrays, one per column,
rather than an array of objects, one per row. Logins, labels and event
types are indexes into small lookup lists (plain arrays of strings), and
repos are indexes into the repos table. Filtering is picking a set of
indexes. A lookup list becomes a table when its entries get attributes,
as repos did for the standards' names. Storing by column keeps the file
small (no key repeated on every row) and lets the browser load columns
straight into typed arrays; a join is an array lookup. Expected size: about
10,000 items and tens of thousands of events, a few MB of JSON before
compression.

**One JSON file** holds `meta`, the lookup lists and every table, so one
request returns one build's data and `meta` always matches the tables.
Split it only when a table gets large and some pages don't need it
(comment and review events are the likely first case): by what pages
need, with `meta` in the file every page loads first and each file
carrying the build's id. It's `build/data.json`, built when the site is
deployed, not committed ("First version", above).

## In the browser

- **All in memory.** The tables are loaded whole and every control change
  recomputes from them; filtering and summing 10,000 rows takes about a
  millisecond. No IndexedDB, Web Worker or in-browser database. One
  loader caches each file's promise, so views sharing a file
  fetch it once.
- **Kept between visits:** the data only in the HTTP cache (GitHub Pages
  sends `max-age=600` and ETags; a manifest of file hashes can add a
  `?v=` to each URL if stale data after a deploy is a problem); the view
  (date range, repos, metric) in the URL, so views can be shared;
  preferences such as the theme in `localStorage`, wrapped in try/catch,
  with nothing depending on them.
- **Load once, switch instantly.** The app loads the data file once;
  every view after that is computed from memory, with no request. If the
  file is ever split, heavier parts load when a view first needs them.

## Time

Data is daily (UTC); binning is a display choice.

- **Rolling windows evaluated every day** are the default for charts:
  each day's point is the sum, median or distinct count over the trailing
  28, 91 or 364 days (multiples of 7, so weekdays and weekends even out),
  91 by default. Graphs change every day, and there's no partial current
  period. They lag and smear a burst over the window, which is why the
  length is a choice.
- **Warm-up.** A rolling series starts `N − 1` days after the window
  does: the trailing 12 months of "people doing 50% of the work" starts
  on 2022-12-31.
- **Calendar bins** (month, quarter, year) for bar charts and tables,
  where exact figures are wanted, computed in the browser from the same
  daily data.
- **Durations of recent items are provisional**, as some are still
  waiting: the last 7 days of "unanswered within 7 days" are marked so.

## Metrics

Each metric is defined once, in a registry the pages, the metric picker,
the hover text and the docs all read: id, label, a one-line definition,
unit, kind (below), the event types it uses, and a version, bumped with
a decisions-log entry when the definition changes.

| Kind | Examples | A day's point |
|---|---|---|
| Flow | PRs merged, reviews, comments | Count of events over the trailing window |
| Stock | Open issues and PRs, backlog by age, items stalled on a label | State at the end of the day, replayed from `_carried_in`, `_created`, `reopened` and `closed` |
| Duration | Time to first response | Median, with the share unanswered after 7 days, over items whose clock started in the trailing window |
| Non-additive | Distinct reviewers, people doing 50% of reviews and merges | Recomputed over the trailing window from per-person daily counts |

## Frontend

### Stack

- **Svelte 5 and Vite**, built into static pages served by GitHub Pages:
  a page for each view and spec (`reviews/`, `reviews/html/`),
  prerendered with `svelte/server` ("Loading", below), and one script
  and one data file that every page shares. Plain Svelte, not SvelteKit:
  rendering the pages is one short build script, `web/scripts/build.ts`.
- The source lives in `web/`. Deploying runs `python3 -m specstats build`
  and then `npm ci && npm run build` in `web/`, and publishes the result
  (`.github/workflows/site.yml`, after every push to `main` and every
  fetch run). The Vite dev server renders each page on request and
  serves `build/data.json` as `data.json`.
- **Few dependencies:** Svelte, Vite, and `d3-scale`, `d3-shape` and
  `d3-time-format` for the charts; TypeScript and `svelte-check` (with `@tsconfig/svelte` and
  type packages) to check them. All pinned exactly. Anything else needs a
  reason in the decisions log. Unit tests use `node --test` with Node's
  type stripping, so no test framework.
- **TypeScript**, checked with `svelte-check` and `tsc`.

### Views

- **One app, many views.** Each dashboard is a view (open PRs, later
  maintenance load, response times, …), each answering one question. The
  start view introduces the site and links to the views. Switching views
  re-renders from the data in memory, so it's instant.
- Shared components: the data loader, the window subtitle ("2022-01-01
  to 2026-11-17", from `meta`), the date-range, rolling-window and repo
  controls, and the charts. A view is mostly its question, its metrics
  and its charts.
- The spec (27 repos) is the main dimension, and whatwg/html is most of
  the activity, so views need to keep it from flattening the rest:
  per-spec small multiples or tables, and an "all but html" choice.
  Organization is a later, second dimension.

### The URL is the view

Everything that decides what's on screen is in the URL, and nothing else
holds it: the page reads its state from the URL and writes it back. The
view and the spec are in the path, each with its own prerendered page
(GitHub Pages ignores the query string, so only the path can choose a
page); the rest is in the query string.

```
/reviews/html/?from=2023-11-22&to=2026-11-21
/reviews/dom/?from=2022-01-01&to=2026-11-21
```

`web/src/lib/url.ts` parses and writes it, relative to the site's root
(`/spec-stats/` on GitHub Pages):

| Path | |
|---|---|
| `issues/` | the open issues view (since 2026-11-21), all specs; also the site's root (since 2026-11-22), until there's a start view |
| `issues/html/` | one spec, by repo name |
| `reviews/`, `reviews/html/` | the open PRs view (the site's root until 2026-11-22) |

The views are linked in that order: Issues, then Reviews.

| Parameter | Values | Default |
|---|---|---|
| `from`, `to` | the first and last day, `2024-01-01`, as on GitHub's contributors graph; an end left out is the window's, and dates outside it are clamped to it (`range`, a preset, 2026-11-22 to 2026-11-23) | the last year, counted back from the window's end |
| `bin` | `day`, `week` (ISO), `month`, `quarter`: the period of the bars, and of the points the open PRs are drawn at | `auto` |

- **Defaults are left out**, so `/reviews/` is a whole link.
- **Changing a control** replaces the history entry (`replaceState`),
  the spec included, which changes the path without loading its page;
  so dragging a range doesn't fill the back button. **Changing view**
  adds one (`pushState`), so Back returns to the previous chart.
  `popstate` re-reads the URL.
- **Parameters mean the same in every view** that uses them (`from`,
  `to`, `bin`), and so does the spec in the path, so switching views keeps
  the filters.
- **Fixed dates, as on GitHub** (since 2026-11-23): the Period choices
  other than the default write their dates, so a link shows the same
  days after the data is updated. Only the default, the last year, moves
  with the data, so `/reviews/` always shows the latest year. Dates that
  are no choice's (a link from before an update) are shown in the Period
  menu as an extra option, "Custom range", as on GitHub; the tiles give
  the dates.
- **Unknown or invalid parameters are dropped quietly** and the URL
  rewritten without them.
- **Paths that aren't pages get `404.html`**, a static "Page not found"
  page (`src/NotFound.svelte`) linking to the views, with no script or
  data: an unknown view or spec (`reviews/nfc/`, `nope/dom/`). GitHub
  Pages serves it with status 404.
- **Old links aren't kept working** (since 2026-11-22): nobody uses the
  site yet, so the parameters of earlier URL designs (`repo`, `repos`,
  `range`) are unknown parameters like any other.
- **The header is laid out as a standard's** (since 2026-11-23): the
  page's `<h1>`, large and green, is the spec's name ("DOM"), or "WHATWG"
  for all specs; under it, in green, "Living Statistics — Last Updated
  21 November 2026", the data's last day written as the standards write
  it; the icon at the top right, linking to the site's root. The browser's
  address bar is the same green (`<meta name="theme-color">`), as on the
  standards. The controller sets the title as the spec changes.
- **Views are linked under the header**, as large tabs, and the current
  tab is the view's only visible name, with the view's question below
  the tabs. Each link keeps
  the spec and the query string, so switching views keeps the filters.
  **Switching is in place** (since 2026-11-22): the controller handles
  the click (a plain click; with a modifier key it's an ordinary link),
  pushes the URL, and sets the view's question and the current tab; the islands recompute from the data in memory, as for any
  control. `Model` works out each kind's series the first time its view
  is shown. A click before the data has loaded hides the islands
  (`data-pending`) until they're mounted for the new view. Each view
  still has its own prerendered page, for links and reloads.
- Repos in the URL are their `name` (`html`), not indexes, as indexes
  change when repos are added.

### Loading

The first paint shows the whole page but the charts' drawings, from the
HTML alone, and nothing moves after it. On a phone on slow 4G with a 4×
slower CPU, that's about 0.3 s, which is also the LCP, against 0.7 s for a
"Loading…" line and 1.5 s for the page when Svelte built it in the
browser (until 2026-11-20); the charts follow at about 1.0 s (1.1 s
before the data file's compact layout, 2026-11-20).

- **Prerendered pages.** `web/scripts/build.ts` renders a page for each
  view and spec (`src/page.ts`, `src/Page.svelte`) with the values for
  the default range: header, controls, tiles, legends, tables and
  footer, and the charts as empty boxes of their final height
  (`AREA_HEIGHT` and `BARS_HEIGHT` in `lib/chart.ts`). The CSS is
  inline, so the HTML, about 10 KB gzipped, is all the first paint
  needs; even the header's icon is in it, as a `data:` URL made from
  `public/favicon.svg`. The site's root is a copy of `issues/`, the
  default view, whose controller rewrites the URL to `issues/`. Links are absolute paths from the site's root on its host,
  `SITE_BASE`, `/spec-stats/` unless set, as `404.html` is served at
  any depth. (No `<base>`: it would make `#footer`, below, point at
  another page.)
- **The controller**, `src/controller.ts`, is plain TypeScript, built
  into one small script (5 KB) inlined into every page after the view,
  before the footer. It owns the URL and the form controls for the life
  of the page, and nothing else: it reads the state from the URL, sets
  the controls (their labels, such as "Auto (week)", included) and the
  title, handles the controls' events and writes the URL back. The
  controls are the one part that must be right, and work, before Svelte
  has loaded; their labels come from `stateText()` in `lib/texts.ts`,
  which the islands use too, so the two agree. Running it costs about 5 ms
  of CPU. It shows no dates, but it bundles the summary tiles' ("Open on
  Nov 21, 2026"), which `stateText()` makes with `longDate()` in
  `lib/format.ts`. That's written by hand: `Intl`'s first use costs tens
  of milliseconds on the throttled phone (54 ms for an
  `Intl.DateTimeFormat`), and `d3-time-format` would add about 11 KB to
  the controller. Nothing else uses `Intl` either: the islands name
  periods with `d3-time-format`, which has its own en-US names, so their
  mount doesn't pay that cost (about 27 ms with month periods, when they
  used `toLocaleString`).
- **Before the first paint.** `<link rel="expect" href="#footer"
  blocking="render">` holds rendering until the footer is parsed, which
  is after the controller has run, so no paint shows the prerendered
  state where the URL asks for another, however the HTML arrives. The
  target is the footer, not the controller's own `<script>`: an element
  counts as parsed at its start tag, and the script's text can still be
  in the next network packet. Browsers without `rel="expect"` (Chromium
  has it) paint a page this small whole in practice.
- **Islands.** Everything else that changes with the state is a Svelte
  component in `src/islands/`, one per section: the summary tiles, the
  open PRs (or issues) panel, the merges (or closes) panel, the PRs (or
  issues) opened panel (each panel its heading, legend,
  chart and table; the two bar panels share `components/BarsPanel.svelte`) and the by-spec table, which shows itself for all
  specs only. The header, the view's question, and the footer
  are static HTML, the title and question set by the controller. `src/islands/index.ts` maps each `data-island` name to
  its component; `Page.svelte` prerenders them from it (the charts as
  empty boxes) and `src/main.ts` mounts them from it, so the names can't
  drift apart. Once the data has loaded, `main.ts` mounts each in its
  element, replacing the prerendered content in one task, so nothing is
  painted in between; they then follow the controller's state, through
  one shared model (`lib/model.svelte.ts`). They're mounted, not
  hydrated: replacing them is cheap, and nothing has to match the
  prerendered markup.
- **Links with a query string** get the same page as without, with the
  default range's values. The controller marks the page `data-pending`,
  and CSS hides the islands (`visibility: hidden`, so they keep their
  space) until they're mounted. The controls are right from the first
  paint. (An earlier version also had the controller set the sections'
  dates and periods before the first paint, so only the numbers waited;
  one owner per part was judged simpler.)
- **The data file** is `data-<hash>.json`, named by its contents and
  preloaded by every page, so a page always gets the data it was
  rendered from, even across a deploy.
- **Nothing is measured** before the first paint: what the prerender and
  the controller show comes from the URL and the data's dates only. The
  charts' widths are measured when they're mounted, inside boxes whose
  size is already fixed.
- **No loading message.** If the data can't be loaded, an error appears
  above the view.

### Performance checks

`npm run cwv` (`web/scripts/cwv.ts`, about 3 minutes) loads the built site
in Chromium, served as GitHub Pages serves it, and fails on any Core Web
Vitals regression. The site workflow runs it after every build, so a
regression is never published, and on pull requests. These are lab
checks: timings vary with the machine, so they have generous budgets,
and what the design guarantees is checked exactly.

| Check | How | Budget |
|---|---|---|
| CLS | 58 loads: six sizes, slow and fast, light and dark, the four kinds of URL (one of them an issues page), scrolled, with real scrollbars; every control used on one load per size, switching views included | 0, on every load |
| LCP | Three cold loads of each kind of URL on a throttled phone (Slow 4G, CPU 4× slower) | 1 s, median (about 0.35 s now) |
| LCP in the first paint | The same loads | no later than the first paint, plus 50 ms |
| First paint needs only the HTML | The same loads | no render-blocking request; HTML at most 14 KB gzipped (the first round trip); every request started by the HTML (no chain), the tab icon aside |
| INP | Every control used, at full CPU speed | 200 ms (about 80 ms now) |

INP at 4× slower CPU is reported but not enforced: choosing days for a
year redraws 365 bars and table rows, which takes about 300 to 450 ms
there. The checks were tested against regressions: dropping the data
file's preload fails as a chain, and dropping the charts' fixed heights
fails CLS. The browser is Chrome for Testing, the full Chrome build that
Playwright pins to its own version (Chrome 158 for Playwright 1.65), in
Chrome's headless mode, rather than Chrome Headless Shell, the separate
build Playwright uses for headless by default. CI installs it with
`npx playwright install --with-deps --no-shell chromium`;
`CHROMIUM_PATH` runs another Chrome.

### The open PRs view

Since 2026-11-19 the view has two charts, and since 2026-11-22 three,
one above the other on the same time axis, over the last year by default:

- **Open PRs at the end of each period, by year opened.** A stacked area,
  oldest at the bottom: one layer for each of the last five calendar
  years, and one for every PR opened before them ("before 2022"). A layer
  only shrinks once its year is over, so clearing old PRs shows as its
  layer thinning. Drafts are counted (since 2026-11-23; before, only PRs
  ready for review were), as in a search for `is:pr is:open`.
- **PRs opened per period, by time to close** (since 2026-11-22), on the
  same axis and periods as the merges (the third chart until it was moved
  above them, the same day): each PR at the day it was created, split by its time to close: closed within 1 week, closed
  later, or still open (until 2026-11-22: within 1 day, in 1–7 days, or
  open more than 7 days). A merge is a close. Of the 3,513 PRs opened
  from 2022-01-01 to 2026-11-21, 61%, 26% and 13%; whatwg/html's 1,868,
  54%, 31% and 14%. The bands are the same for issues, so the two compare.
  - PRs opened in the window's last 7 days may still be closed within a
    week, so periods ending in them are **provisional**: shaded like a
    partial period, and marked "provisional" in the tooltip and the
    table (`SETTLE_DAYS` in `lib/flow.ts`). After that only "closed
    later" and "still open" change, as old PRs are closed, which they
    never stop doing; that isn't marked.
  - PRs opened before the window aren't counted.

- **PRs merged or closed per period, by time open.** Stacked bars
  ("by time from ready for review to merge", and merges only, until
  2026-11-23):
  - The split is within 1 day, 1–10 days, and more than 10 days, stacked
    slowest at the bottom, so the fastest (lightest) is on top as the
    newest year is in the chart above. For
    whatwg/html's 1,310 merges since 2022 those breaks gave near thirds,
    timed from ready for review: 34%, 34% and 32%
    (`docs/response-metrics.md`). Since 2026-11-23 the time runs from
    creation, so a PR's time as a draft counts: 131 of the 2,646 merged
    PRs were created as drafts.
  - PRs closed without merging are a fourth layer, gray (`--closed`),
    on top of the merges, with no split by time (since 2026-11-23), so
    the change in open PRs over a period is the PRs opened in it less
    those merged or closed. The tile still counts merges only.
  - Each bar is a calendar period: a day, an ISO week, a month or a
    quarter, chosen with the "Per" select (`bin` in the URL).
  - "Auto", the default, picks the smallest of week, month or quarter
    that gives at most 54 bars (a year of ISO weeks can touch 54): weeks
    up to a year, months up to four and a half years, quarters beyond.
    It's chosen from the range alone, not the chart's width, so the page
    can show it before anything is measured ("Loading"; until
    2026-11-20 it kept bars at least 8 px wide, which made it weeks on a
    desktop and months on a phone). It never picks days, as a day's
    merges are mostly 0 to 3; they can be chosen.
  - Bars only a few pixels wide (days over years) lose the gap between
    them, so they don't disappear into it.
  - Periods the range cuts short (the current week, or a range starting
    mid-week) are shaded and marked "partial". Days are always whole.

The area follows the bars' period (since 2026-11-20): it's drawn
through the open count on the range's first day and at the end of each
period, so one point a week, month or quarter, or every day with days.
That makes it smoother without smoothing the data. Each point is an
exact count, joined with `curveMonotoneX`. The tooltip still gives every
day's counts, and the y-scale fits every day, so it doesn't change with
the period. A burst inside a period (October 2026's batch of 20 PRs from
one contributor in a week) shows as a rise from one period's end to the
next.

Both charts show age the same way: one green, light for new and darker
with age, in light and dark mode alike. That covers the year-opened
layers (the current year lightest) and the merge bands (within 1 day
lightest). Each ramp is validated as an ordinal ramp against the page
in both modes (`--cohort-*`, `--age-*` in `app.css`).

### The open issues view

Since 2026-11-21, `issues/` mirrors the open PRs view for issues, with
the same controls, layout and colors:

- **Open issues at the end of each period, by year opened**, the same
  layers. Issues have no drafts, so every open issue counts. About half
  of the open issues (2,158 of 4,219 on 2026-11-20) were opened before
  2022, so the oldest layer is the largest.
- **Issues opened per period, by time to close** (since 2026-11-22), as
  for PRs: closed within 1 week, closed later, or still open. Of the
  4,069 issues opened from 2022-01-01 to 2026-11-21, 24%, 26% and 51%;
  whatwg/html's 2,608, 23%, 26% and 50%.
- **Issues closed per period, by time open**, from creation to the last
  close: within 1 week, 1 week to 90 days, more than 90 days. For
  whatwg/html's 1,569 issues closed since 2022 those breaks give 39%,
  28% and 33% (the median is 15 days), as the merge bands were chosen
  for near thirds. Every close counts, whatever its `state_reason`
  (completed, not planned or duplicate); an issue closed and later
  reopened isn't counted until it's closed again.
- The tiles: issues open at the end of the range, the change over it,
  and issues closed in it; and the by-spec table.

`Model` (`lib/model.svelte.ts`) works out each kind's counts the first
time its view is shown: `lib/open.ts` counts the items of one kind, and
`lib/flow.ts` counts merges or closes, and items opened, with their
bands.

### Charts

Hand-written SVG components, using `d3-scale` and `d3-shape` for scales,
ticks and paths, and `d3-time-format` for the periods' names ("November 2026",
"2026-W47"; `periodName()` in `lib/names.ts`); no chart library.

- **Lines and areas use `curveMonotoneX`.** It passes through every
  point drawn and never overshoots, so the chart rounds corners without
  smoothing the data.
- **One time axis for charts shown together.** `StackedArea` and
  `StackedBars` share their margins (`web/src/lib/chart.ts`): wide
  enough on the right for the area chart's direct labels, which are
  dropped below 480 px, on phones, so the plot gets the width. The axis
  runs from the start of the first day to the end of the last, each
  day's value sits at its middle, and a bar covers its whole days.
- **Tick marks on both axes**, 5 px outside the plot at each label but
  the y axis's 0 (the x axis line is there), so
  the start of a year or month is clear. About 1,800 daily points a series is
well within what SVG draws smoothly, and owning the markup gives full
control of type, color and axes. What a library would have given is
ours to build and test:

- a crosshair with a tooltip on time series, and a tooltip per mark on
  bars, with hit targets larger than the marks;
- keyboard access to the same values, and a table view of every chart;
- a legend for two or more series, plus direct labels where they fit;
- light and dark themes, each with its own colors checked for contrast
  and color-vision deficiency.

### Look

The WHATWG's look, made more modern: the green of the WHATWG logo as the
one accent, a calm, mostly monochrome page, and typography that puts the
text first, nothing decorative. On top of that, careful type at a
comfortable reading width, generous whitespace, thin chart lines with few
gridlines, a real dark mode, and a sticky bar for the range and repo
filters.

The filter bar is one row of same-sized controls (since 2026-11-18, after
the maintainer found the first version hard to use): a Spec select, a
Period select (Last year, Last 3 years, All; buttons until 2026-11-23),
and a Per select. There's no control for custom dates (removed
2026-11-22: it didn't work on phones), and no "Copy link" button: the
address bar is the link.

- **Spec** is a native `<select>`: All specs, or one spec, the two
  common cases, each one choice (type-ahead works, and phones show their
  own picker), and the URL holds at most one (`repo=html`). Clicking a
  spec in the by-spec table also selects it. The by-spec table is shown
  only when more than one spec is (since 2026-11-20): for one spec it
  would repeat the tiles.
- Patterns follow Modern Web Guidance (GoogleChrome/modern-web-guidance)
  where it covers them.

`docs/PRODUCT.md` has the
users, personality and principles the design follows.

What the WHATWG's own styles use (read on 2026-11-18 from the
whatwg/whatwg.org repo, which holds both sites: `whatwg.org/style/shared.css`,
`resources.whatwg.org/standard.css`, `spec.css` and `logo.svg`):

- **Green** `#3c790a` (the logo, and the specs' header links); the site's
  `--whatwggreen` is `#3a7908`, with buttons graded to `#00981b`.
- **Type:** the system sans-serif stack (`-apple-system,
  BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`);
  no web fonts.
- **Page:** black text; whatwg.org on a light gray (`rgb(235, 235, 235)`)
  with a 900px column; the specs on white, up to 80em wide; plain
  underlined links, blue `#00f` and visited `#0e388c` on whatwg.org.
- **The specs' header links** each have a color: comms blue `#165fcc`,
  feedback red `#ff3e3a`, changes teal `#54b29a`, misc orange `#ffa32d`.
- **Dark mode:** the specs follow `prefers-color-scheme` (through
  Bikeshed's variables); whatwg.org doesn't.

So spec-stats uses the green `#3c790a` as its one accent (with a lighter
step of the same hue for dark mode, checked for contrast), the same
system font stack, a white page, and a reading column near whatwg.org's.
Chart series colors are a validated categorical palette, not the header
links' colors, which aren't chosen to be told apart in charts. The
header follows the standards' headers (since 2026-11-23: title,
subtitle, icon at the top right, green address bar), but the WHATWG logo
isn't used, and the footer says the site isn't affiliated with the
WHATWG.

The site's icon, `web/public/favicon.svg`, is drawn the way the WHATWG's
spec logos are (`resources.whatwg.org/logo-*.svg`): a 100×100 viewBox, a
white circle (r=45) with a 10-wide `#3c790a` ring, and one solid green
glyph, here three rising bars. It's an icon of the same family, not the
WHATWG logo itself. The header shows the same file at its top right, where a
standard shows its logo, so it keeps its white circle in dark mode too.
