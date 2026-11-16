# spec-stats: WHATWG spec maintenance health

spec-stats is meant to build public dashboards about how the
[WHATWG](https://whatwg.org/) Living Standards are maintained, and by whom,
from public data, following [cosh](https://github.com/RByers/cosh)
(Chromium Open Source Health).

**For now it only collects data:** a serial, incremental extractor
mirrors the GitHub activity of the WHATWG repos into `data/github/`. Nothing
is derived or summarized yet, and there are no pages. A first dashboard
(Maintenance load) and its pipeline were drafted and then removed until the
data is in; they're in git at `10edb66` (`specstats/derive.py`,
`specstats/summarize.py`, `web/`, `docs/maintenance-load.md`). Ideas for
dashboards are in [`docs/plan.md`](docs/plan.md).

## Data sources

| Source | What it gives | Status |
|---|---|---|
| GitHub REST API, the repos in `config/repos.txt` | Every issue and PR with their comments, inline review comments, timeline events and reviews (commits and changed files optional); public profiles (approved, not fetched for now) | Approved 2026-11-13. whatwg/dom fetched 2026-11-14; whatwg/html next. Stored in `data/github/` |
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
Operator settings go in `data/private/` (gitignored).

You need a GitHub token, either `GITHUB_TOKEN` in the environment or a
signed-in `gh` CLI. A fine-grained token with no extra permissions is enough
for public repos. Put your contact address in `data/private/settings.json`
(`{"contact": "you@example.com"}`) so it goes in the User-Agent.

```
python3 -m specstats extract --dry-run            # print the plan, fetch nothing
python3 -m specstats extract --repo whatwg/html
python3 -m specstats extract                      # all repos; incremental after the first run
python3 -m specstats extract --max-minutes 60     # stop cleanly after an hour; the next run continues
python3 -m specstats extract --reconcile          # weekly: also re-list every issue/PR (deletions, missed updates)
python3 -m specstats stats                        # what's stored (offline)
python3 -m unittest discover tests
```

The first `extract` fetches each repo's whole history, one issue or PR at a
time; later runs fetch only what changed, and an unchanged repo costs two
requests. It stores what GitHub returns, consistent or not; `python3 -m specstats
check` (offline) then looks for inconsistencies in the stored data, which
may be bugs in the process or GitHub's own. The data is plain JSON files, so `jq`, `grep` and `git log -p` work on it directly. How
updates work, and how holes are caught: [`docs/extraction.md`](docs/extraction.md).

### In GitHub Actions

`.github/workflows/fetch.yml` runs the extractor on demand (Actions →
"Fetch GitHub data" → Run workflow). Each run stops itself after 300
minutes and commits what it fetched to `data/github/`, even if it failed,
and the next run resumes from there. If `main` moved during the run, it
fails without committing, as the collection code may have changed; don't
merge into `main` while a run is going. A backfill bigger than one
hour's budget (whatwg/html: about 10) takes several runs.

- The built-in token is enough: it has had 5,000 requests an hour here
  (each run logs the limit). A run doesn't wait for the hourly limit to
  reset: it stops and commits when the budget is down to its reserve, so
  a backfill is one run an hour (about 4,500 requests each).
- Set a `SPECSTATS_CONTACT` variable to put a contact address in the
  User-Agent.
- Each run's summary page shows what's stored and the cursors
  (`python3 -m specstats stats`).
- The separate "Timeline check" workflow (`python3 -m specstats
  timeline-check`) compares the timeline API with the stored lists for a
  sample of whatwg/dom items, and commits nothing.

## Docs

- [`docs/plan.md`](docs/plan.md): goal, ground rules, decisions log, status and next steps.
- [`docs/extraction.md`](docs/extraction.md): what is fetched, how daily updates work, and the consistency checks.
