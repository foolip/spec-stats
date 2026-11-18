# Site design

How the dashboards will be built from the collected data: what a build
step publishes, what the browser holds, and how time is represented.
Nothing here is built yet. The project is still collecting data
(`docs/plan.md`); this records the design agreed on 2026-11-18 so the
dashboard work starts from it. Decisions and their reasons are in the
decisions log.

## Shape

```
data/github/ ── build (Python) ───▶ build/data.json ──▶ pages (browser)
   raw, both tiers                  items, events,        compute every
                                    users + meta          metric in memory
```

- **Raw:** `data/github/`, as fetched (`docs/extraction.md`).
- **Build:** one Python step (standard library only) reads the raw files
  and writes a few small published tables. Every rule about what the raw
  data means lives here: which raw events count, how an item's state is
  worked out, what's left out, where the timeline starts.
- **Pages:** plain HTML, CSS and ES modules with no JavaScript build step
  (decisions log, 2026-11-13). They read only the published tables and
  compute every metric from them in the browser.

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
- **Opening state.** Items already open when the window starts get a
  synthetic `_carried_in` event dated the window's first day. The build
  works out who was open then by replaying each item's events before the
  window. No other event dated before the window is published.
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

## First version: open PRs

The first page is the number of open PRs over time, per spec. The build
publishes only what that needs, and the tables grow a column or an event type at
a time as later metrics need them:

- **repos**, one row per standard: `name` (`html`, the repo's `name` in
  GitHub's API, and the spec's subdomain) and `standard` (`HTML`, the
  standard's `name` in `config/db.json`, as is: no "Standard" added), so
  pages show HTML rather than html.
- **event_types**: `_carried_in`, `_created`, `closed`, `reopened`. No `merged`:
  GitHub records a `closed` event on every merge too (all 154 merged
  whatwg/dom PRs have both), so `closed` alone ends a PR's open span.
- **items**, PRs only: repo, and number (for links and for checking a
  count against GitHub).
- **events**: day, item, event, sorted by day, item and time (a PR
  reopened and closed on one day has both, in that order). Only changes of state
  are published (a second `closed` without a `reopened` between is left
  out), and a PR with no event in the window isn't an item.
- **meta**: the window.

`python3 -m specstats build` (`specstats/build.py`) writes it to
`build/data.json`, which isn't committed: whatever deploys the site runs
the build. `events.day` counts UTC days from `meta.from`, day 0. The
window ends on the last full UTC day before the newest time any repo's
`state.json` shows it was listed at: the newest `updated_at` seen
(`items.cursor`) or the last reconcile's start (`items.rows`). Every run
lists every repo, so that's when the data was last complete; if fetching
stops, the window stops with it. A repo whose listings aren't done, or
with nothing stored (whatwg/nfc), is left out. A PR whose events disagree
with its own state follows its state: a `closed` at its `closed_at` (12
PRs on 2026-11-18), or a `reopened` at its `updated_at`.

On 2026-11-18 it held 26 repos, 3,727 PRs and 7,098 events in 108 KB,
2022-01-01 to 2026-11-17: 242 PRs open at the start and 560 at the end,
each repo's end count equal to its stored open PRs.

No users, labels or other lookups yet. Whether drafts count as open is
decided with the metric's definition.

## Published tables

A star schema: one table of facts (events) and tables describing the
things they refer to (items, users, repos).

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
  - detail: `commented`, `reviewed` (with its state), `review_requested`,
    `labeled`, `unlabeled`, `ready_for_review`, `convert_to_draft`, …
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
  loader caches each file's promise, so pages and sections sharing a file
  fetch it once.
- **Kept between visits:** the data only in the HTTP cache (GitHub Pages
  sends `max-age=600` and ETags; a manifest of file hashes can add a
  `?v=` to each URL if stale data after a deploy is a problem); the view
  (date range, repos, metric) in the URL, so views can be shared;
  preferences such as the theme in `localStorage`, wrapped in try/catch,
  with nothing depending on them.
- **Load only what a page needs**, and heavier files only when a control
  asks for them.

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

## Pages

- A landing page, and one page per dashboard, each answering one
  question.
- A shared module for loading, the window subtitle, the date range,
  rolling-window and repo controls, URL state and charts, so each page is
  mostly its question, its metrics and its charts.
- **The main dimension is the spec** (27 repos), and whatwg/html is most
  of the activity, so views need to keep it from flattening the rest:
  per-spec small multiples or tables, and an "all but html" choice.
  Organization is a later, second dimension.
