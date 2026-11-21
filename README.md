# spec-stats: WHATWG spec maintenance health

spec-stats is meant to build public dashboards about how the
[WHATWG](https://whatwg.org/) Living Standards are maintained, and by whom,
from public data, following [cosh](https://github.com/RByers/cosh)
(Chromium Open Source Health).

**For now it only collects data:** a serial, incremental extractor
mirrors the GitHub activity of the WHATWG repos into `data/github/`. The
site has one view so far, open PRs over time by year opened, with the
PRs merged each week or month below (`web/`, published to GitHub Pages). A first dashboard
(Maintenance load) and its pipeline were drafted and then removed until the
data is in; they're in git at `10edb66` (`specstats/derive.py`,
`specstats/summarize.py`, `web/`, `docs/maintenance-load.md`). Ideas for
dashboards are in [`docs/plan.md`](docs/plan.md).

## Data sources

| Source | What it gives | Status |
|---|---|---|
| GitHub REST API, the repos of the standards in `config/db.json` | Every issue and PR's listing row; for those updated since 2022-01-01 (`config/fetch.json`) or still open, also their comments, inline review comments, timeline events and reviews; public profiles (approved, not fetched for now) | Approved 2026-11-13. whatwg/dom fetched 2026-11-14; whatwg/html next. Stored in `data/github/` |
| whatwg/sg's `db.json` (raw.githubusercontent.com) | The Living Standards, whose repos are fetched; copied as is into `config/db.json` | Approved 2026-11-17. One request, by `python3 -m specstats sync-db` when run by hand |
| The WHATWG's site and spec stylesheets and logo (from the whatwg/whatwg.org repo) | Colors and fonts for the frontend's look | Approved 2026-11-18. Read once, by hand; not stored |
| git history of the spec repos | Diffs of spec text (how much prose is written) | Deferred: API data first (2026-11-13) |
| Browser bug trackers (crbug, Bugzilla, WebKit) | Status of implementation bugs linked from PRs | Not approved |
| wpt.fyi | Test results for tests linked from PRs | Not approved |

A new source, or more data from an existing one, needs explicit approval
before anything is fetched ([`docs/plan.md`](docs/plan.md), ground rules).

## Usage

The extractor uses the Python standard library only. Everything fetched is
committed as JSON files in `data/github/`, laid out like the API paths
(`whatwg/html/issues/1234/index.json`, `whatwg/html/issues/1234/comments.json`,
…).
Local-only output, such as the timeline check's, goes in `data/private/`
(gitignored).

You need a GitHub token, either `GITHUB_TOKEN` in the environment or a
signed-in `gh` CLI. A fine-grained token with no extra permissions is enough
for public repos.

```
python3 -m specstats extract --dry-run            # print the plan, fetch nothing
python3 -m specstats extract --repo whatwg/html
python3 -m specstats extract                      # all repos; incremental after the first run
python3 -m specstats extract --max-minutes 60     # stop cleanly after an hour; the next run continues
python3 -m specstats extract --reconcile          # weekly: also re-list every issue/PR since the start (deletions, missed updates)
python3 -m specstats stats                        # what's stored (offline)
python3 -m specstats sync-db                      # copy whatwg/sg's db.json into config/db.json
python3 -m specstats build                        # build/data.json, the file the site reads (offline; not committed)
python3 -m unittest discover tests
```

The site (`web/`, Svelte, Vite and TypeScript; `docs/site-design.md`,
"Frontend") reads `build/data.json`, so run `build` first:

```
cd web && npm ci
npm run dev                                       # localhost:5173/reviews/, each page rendered on request
npm run check && npm test                         # svelte-check and tsc; unit tests (node --test)
npm run build                                     # web/dist/: the prerendered pages, script and data file
npm run cwv                                       # Core Web Vitals budgets for web/dist/ (about 3 minutes; needs Chrome for Testing: npx playwright install --no-shell chromium)
```

The first `extract` fetches each repo's issues and PRs updated since
`updated_since` in `config/fetch.json` (2022-01-01), and the open ones
however old, one at a time, each
with its whole history; the weekly `--reconcile` run also stores every
other item's listing row (no comments or events); later runs fetch only what changed, and an unchanged repo costs two
requests. It stores what GitHub returns, consistent or not; `python3 -m specstats
check` (offline) then looks for inconsistencies in the stored data, which
may be bugs in the process or GitHub's own. The data is plain JSON files, so `jq`, `grep` and `git log -p` work on it directly. How
updates work, and how holes are caught: [`docs/extraction.md`](docs/extraction.md).

### In GitHub Actions

`.github/workflows/fetch.yml` runs the extractor every hour (at :48),
with `--reconcile` once a week (Mondays at 03:18 UTC), and on demand (Actions → "Fetch GitHub data" → Run workflow). Each run stops itself after 50
minutes and commits what it fetched to `data/github/`, even if it failed,
and the next run resumes from there. If `main` moved during the run, it
fails without committing, as the collection code may have changed; don't
merge into `main` while a run is going. A backfill bigger than one
hour's budget takes several runs, one an hour.

- The built-in token is enough: it has had 5,000 requests an hour here
  (each run logs the limit). A run doesn't wait for the hourly limit to
  reset: it stops and commits when the budget is down to its reserve, so
  a backfill is one run an hour (about 4,500 requests each).
- Each run's summary page shows what's stored and the cursors
  (`python3 -m specstats stats`).
- The separate "Timeline check" workflow (`python3 -m specstats
  timeline-check`) compares the timeline API with the stored lists for a
  sample of whatwg/dom items, and commits nothing.
- The "Listing check" workflow (`python3 -m specstats listing-check`)
  compares the items listing's rows with `GET /issues/{n}` for a sample
  of a repo's items, and commits nothing.
- The "Site" workflow (`.github/workflows/site.yml`) runs `build` and the
  site's checks, tests and build, and publishes `web/dist/` to GitHub
  Pages: on every push to `main`, after every fetch run, and on demand.
  Pull requests get the checks and build without publishing. It needs
  Settings → Pages → Source set to "GitHub Actions".

## Docs

- [`docs/plan.md`](docs/plan.md): goal, ground rules, decisions log, status and next steps.
- [`docs/extraction.md`](docs/extraction.md): what is fetched, how daily updates work, and the consistency checks.
- [`docs/site-design.md`](docs/site-design.md): how the dashboards will be built: published tables, data in the browser, time and metrics.
- [`docs/response-metrics.md`](docs/response-metrics.md): research on triage, first-response and resolution metrics, with a proposal.
