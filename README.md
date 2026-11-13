# spec-stats: WHATWG spec maintenance health

spec-stats builds public dashboards about how the
[WHATWG](https://whatwg.org/) Living Standards are maintained, and by whom,
from public data. Each dashboard is a page of one static site (`web/`), and
a landing page (`web/index.html`) links to them all. The approach follows
[cosh](https://github.com/RByers/cosh) (Chromium Open Source Health): a
throttled, cached extractor per data source, a lossless raw cache kept
locally, small committed summaries, and pages that read only the summaries.

## Dashboards

| Dashboard | Page | Question | Data sources |
|---|---|---|---|
| Maintenance load | `web/maintenance.html` | Who reviews, merges and triages spec changes, by organization and spec, and how few people carry each spec? | GitHub API |

Ideas for later dashboards are in [`docs/plan.md`](docs/plan.md).

## Data sources

| Source | What it gives | Status |
|---|---|---|
| GitHub GraphQL API, the repos in `config/repos.txt` | PRs, reviews, issues, comments, labels; public profiles (for `company`) | Approved 2026-11-13; extractor written, not run yet |
| git history of the spec repos | Commits | Not approved |
| Browser bug trackers (crbug, Bugzilla, WebKit) | Status of implementation bugs linked from PRs | Not approved |
| wpt.fyi | Test results for tests linked from PRs | Not approved |

A new source, or more data from an existing one, needs explicit approval
before anything is fetched ([`docs/plan.md`](docs/plan.md), ground rules).

## Usage

The pipeline uses the Python standard library only. Raw and derived data go
in `data/private/` (gitignored). Summaries go in `summaries/` and are
committed.

You need a GitHub token, either `GITHUB_TOKEN` in the environment or a
signed-in `gh` CLI. A fine-grained token with no extra permissions is enough
for public repos. Put your contact address in `data/private/settings.json`
(`{"contact": "you@example.com"}`) so it goes in the User-Agent.

```
python3 -m specstats extract                      # dry run: prints the plan
python3 -m specstats extract --repo whatwg/dom --go
python3 -m specstats extract --since 2021-01-01 --go   # all repos, incremental
python3 -m specstats users --go                   # public profiles of everyone seen
python3 -m specstats derive                       # build derived.sqlite (offline)
python3 -m specstats summarize                    # write summaries/ (offline)
python3 -m unittest discover tests
python3 -m http.server 8000                       # then open http://localhost:8000/web/
```

Re-running `extract` fetches only PRs and issues updated since the last run.

## Docs

- [`docs/plan.md`](docs/plan.md): goal, ground rules, decisions log, status and next steps.
- [`docs/maintenance-load.md`](docs/maintenance-load.md): what the Maintenance load dashboard counts, and its known limits.
