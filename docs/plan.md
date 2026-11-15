# spec-stats plan, decisions and status

This is the entry point for anyone (a person or a fresh Claude session)
picking the project up. Read this, then `README.md`, then
`docs/extraction.md`.

## Goal

A set of dashboards about the health of WHATWG spec maintenance, published
as one static site, each answering one question from public data. Each
data source gets its own extractor, with its raw data kept losslessly as
committed JSON files (`data/github/` for GitHub).

**Current phase: collecting data only.** No deriving, summarizing or
pages until the data is in and checked. A first dashboard was drafted and
removed on 2026-11-14 (decisions log); its last version is at commit
`10edb66`:

- **Maintenance load:** who reviews, merges and triages changes to each
  Living Standard, by organization over time; how few people carry each
  spec (people doing 50% of reviews and merges in the last 12 months); and
  how long issues and PRs wait for a first response. Definitions were in
  `docs/maintenance-load.md`.

## Ground rules

1. **Fetch only what has been approved.** Approved on 2026-11-13: the GitHub
   REST API for the WHATWG repos in `config/repos.txt`: all activity on
   their issues and PRs (comments, inline review comments, timeline events,
   reviews, commits, changed files) and the public profiles of accounts
   seen in them. Not approved: git clones (deferred on 2026-11-13: API data
   first), browser bug trackers, wpt.fyi, GH Archive, and any repo outside
   `whatwg/`.
   - `extract --dry-run` prints what a run would fetch without fetching.
2. **Be gentle with GitHub.**
   - Serial requests, one at a time, with no gap between them (since
     2026-11-14; it was at least 1 s apart).
   - Back off on 429/5xx and secondary rate limits, honoring
     `Retry-After`; pause when the hourly budget drops below 500 requests.
   - Incremental: fetch only what changed since the last run, with ETags so
     unchanged listings are free 304s (`docs/extraction.md`).
   - Identify ourselves: the User-Agent carries the operator's contact
     address from the gitignored `data/private/settings.json`.
3. **Publishing per-person data.** The raw GitHub data, which includes
   logins, bodies and profiles, is committed publicly in `data/github/`
   (confirmed by the maintainer on 2026-11-14). Whether per-person counts
   go on dashboards, as cosh does (its ground rule 3), is to be decided
   when there are dashboards. Affiliations that aren't backed by a public
   source need approval before they're committed either way.
4. **Credentials:** a GitHub token in `GITHUB_TOKEN` or from `gh auth token`.
   Never print or commit it.
5. **Never point fingers.** A small "people for 50%" number is a fact about a
   spec's resilience, not a judgment of the people involved. Pages present
   it that way. No figures about tone or "slow" individuals.

## Decisions log

| Date | Decision | Why |
|---|---|---|
| 2026-11-13 | Repo `foolip/spec-stats`; first dashboard is Maintenance load; first source is the GitHub API for `whatwg/*` | Maintainer's choice |
| 2026-11-13 | ~~GraphQL per item: one query gets a page of PRs with their reviews and comments~~ Superseded the same day, below | |
| 2026-11-13 | Fetch all activity on issues and PRs, not a chosen subset; metrics decide what to use | Filtering at fetch time is the one choice that's expensive to undo (a full backfill) |
| 2026-11-13 | ~~REST listings of whole repos (issues, comments, review comments, events)~~ (superseded on 2026-11-15: items by number, events from the repo-wide listing), ~~plus batched GraphQL for reviews, commits and files~~ (superseded below: REST only) | REST supports `since` and ETags, so a daily run of an unchanged repo is four free 304s |
| 2026-11-13 | Re-read a day of overlap on every run, save cursors per page, ~~check comment counts per item~~, reconcile every number weekly, and fail on count mismatches (counts dropped on 2026-11-15: lists are refetched whole with their item, and whatwg/dom has items whose count never matches, e.g. #126, 43 vs 40) | Stopping at the last-seen item trusts the API to be perfect; these find and fill holes instead (`docs/extraction.md`) |
| 2026-11-13 | **REST only**, no GraphQL: per-PR requests for reviews instead of batched queries | REST returns whole objects, so everything is stored without maintaining field lists; one representation, ETags and `since` throughout. Costs a longer one-time backfill (roughly 2 requests per PR) |
| 2026-11-13 | Per-PR commits and files are optional (`config/fetch.json`), off for now | Not sure they're needed; each resource is tracked separately, so turning one on later fetches only that |
| 2026-11-13 | Raw objects are stored as plain JSON text, uncompressed (in files since 2026-11-14) | The maintainer wants to query the database and see the JSON directly. A few GB is fine |
| 2026-11-13 | Keep previous versions of changed objects (~~`history`~~ git, since 2026-11-14) | Edits, label changes and profile changes are otherwise lost; future analyses may want them, and it's cheap |
| 2026-11-13 | Reconcile by issue number: every number from 1 to the highest is stored or recorded as deleted/transferred | Numbers are one sequence per repo, so completeness can be checked exactly |
| 2026-11-14 | Page listings by keyset (`since` just before the newest row seen), not offset links | An offset page skips a row whenever an already-read item is updated mid-listing; that would happen during a long backfill. Also avoids GitHub's deep-pagination limit |
| 2026-11-14 | ~~Start with whatwg/dom only~~ (whatwg/html since 2026-11-15), fetched by a manually triggered GitHub Actions workflow; ~~the raw cache is kept as a workflow artifact (90 days)~~ the data is committed (below) | Maintainer's instruction: populate and check one repo first |
| 2026-11-13 | PR diffs and git history deferred | Spec text written is interesting, but needs git (API patches are truncated for large PRs); API data first |
| 2026-11-13 | Response time counts from ready-for-review for PRs opened as drafts, and "unanswered" means no response within 7 days | From the earlier whatwg/html prototype: responses during a draft aren't triage, and a median alone hides items nobody answers |
| 2026-11-13 | Merges are split into self and other; generated boilerplate comments are left out | Same prototype: a self-merge isn't review work, and PR preview comments aren't comments |
| 2026-11-13 | Count each action in the month it happened (review submitted, comment written, merge), not when the PR closed | Same lesson as cosh's metric_version 3: close-week counting smears long-running PRs |
| 2026-11-13 | Org from the profile `company` field plus `config/affiliations.json` overrides | The WHATWG has no affiliations file like Chromium's; `company` is public and self-declared |
| 2026-11-13 | Self-reviews and bots are left out; the PR author's comments aren't "responses" | Replies in one's own review threads are recorded as reviews, but they aren't review work |
| 2026-11-13 | Web pages are plain HTML, CSS and ES modules, with no build step | Small enough not to need one |
| 2026-11-14 | Stay with Python (standard library only), with our own small REST client rather than a wrapper library | Maintainer's choice. The extractor needs raw JSON, ETags, `since` with overlap and per-page cursors, which wrappers hide or don't help with; Octokit's throttling plugin (TypeScript) was the main thing given up |
| 2026-11-14 | Issues and PRs (the `/issues` listing) are committed to this repo, one file per item: `data/github/{owner}/{repo}/issues/{number}.json`, pretty-printed (2-space indent, GitHub's field order, trailing newline). ~~SQLite stays the working cache~~ (superseded below) | Maintainer's choice. A file per item keeps each update a small diff and every file small; git keeps the history and hosts the data long term, and a run can resume from the files if the artifact is gone. One directory for both kinds, as they share one number sequence |
| 2026-11-14 | **No SQLite for raw data.** Everything fetched is committed as files laid out like the API paths (`issues/{n}.json` (since 2026-11-15 `issues/{n}/index.json`), `issues/{n}/comments.json`, `pulls/{n}/reviews.json`, `users/{login}.json`, …) plus a `state.json` per repo; git replaces the `history` table and the workflow artifact. Events are stored without their embedded copy of the issue. SQLite may come back for crunching | Maintainer's choice: public, browsable data in one place with its history, and no second copy to keep in sync. The embedded issue is a snapshot of `issues/{n}.json` at fetch time, repeated on every event |
| 2026-11-14 | The fetch workflow only fetches and commits; it doesn't run `derive` or `summarize` | Maintainer's instruction: the raw data isn't to be summarized yet. ~~The code stays for later~~ removed (next row) |
| 2026-11-14 | Removed `derive`, `summarize`, org attribution (`orgs.py`, `config/affiliations.json`, `companies.json`, `bots.txt`), `summaries/`, `web/` and `docs/maintenance-load.md`; last version at `10edb66` | Maintainer's instruction: collect data first; the dashboard will be reworked anyway (next steps) |
| 2026-11-14 | Runs have a deadline (`--max-minutes`); the workflow stops fetching at 300 minutes and then commits | Without one, a long backfill (or an hour-long rate-limit pause) runs into the job's time limit and is cancelled, and whether the commit step still runs then isn't something to rely on. Stopping only between requests loses nothing |
| 2026-11-14 | Public profiles aren't fetched for now (the `users` command is removed), though they stay approved; `reconcile` is `extract --reconcile`, so a run is one command | Profiles were only needed for `company`, for org attribution, which went with `derive`. They hold only current values, so fetching them when a dashboard needs them loses little. One command means one deadline and a simpler workflow |
| 2026-11-14 | `extract` fetches by default; `--dry-run` opts out (replaces cosh's `--go` opt-in) | Maintainer's choice: fetching approved public data is harmless, and an opt-in switch on the only fetching command, run daily, adds nothing |
| 2026-11-14 | No minimum gap between requests; still serial, with back-off and the hourly reserve | The hourly budget decides throughput anyway, and GitHub asks for serial requests, not slow ones: its secondary limit is 900 a minute for REST, and Octokit's throttling plugin doesn't space out GETs. With a personal token the 1 s gap was the bottleneck (3,600 an hour of 5,000) |
| 2026-11-15 | Removed `data/github/users/` (1,125 profiles fetched on 2026-11-14 before profile fetching was dropped); profiles stay out of the repo until there's a decision on what of them to publish | 438 of them held public email addresses; republishing those in bulk is the riskiest part of the data under GitHub's Acceptable Use Policies and GDPR. They remain in git history (commit `d2eb8fc`) |
| 2026-11-15 | An issue or PR is stored as `issues/{n}/index.json` and `pulls/{n}/index.json`, not `issues/{n}.json` and `pulls/{n}.json`; existing files moved | Maintainer's choice: everything for one number is in one directory |
| 2026-11-15 | Requests send `X-GitHub-Api-Version: 2026-03-10` (was `2022-11-28`) | Maintainer's instruction: use the current REST API version. Stored objects fetched before this were returned under `2022-11-28` |
| 2026-11-15 | **Items are fetched by number:** the backfill runs `GET /issues/{n}` and everything for that number (comments, and for PRs `pull`, reviews, inline comments) for n = 1 … highest; later runs list items updated since the cursor and refetch each changed item the same way. Lists are replaced whole, not merged | Complete as it goes: every number below the cursor is stored or gone, and stopping and resuming are the same thing. A listing paged by number can skip rows when items are deleted or transferred in mid-read (whatwg/dom #1340 was transferred in, with an older creation date than lower numbers). One API form for every stored object. Costs one request per item more than storing listing rows |
| 2026-11-15 | Redirects aren't followed; a transferred issue is treated like a deleted one (recorded as gone) | Maintainer's choice. Following the redirect fetches from another repo, possibly outside `whatwg/` |
| 2026-11-15 | **Events come only from the repo-wide `/issues/events` listing**, read back to the beginning once, then the new ones each run (a free 304 if none); no per-item event requests. The run fails if GitHub won't page back far enough, or if a closed item has no `closed` event or a merged PR no `merged` event | Fewest requests (one per 100 events). It catches the events that don't move an item's `updated_at` (1,965 of 14,960 in whatwg/dom, mostly `referenced`). It paged back to 2012 for whatwg/dom; whatwg/html, the biggest, is the test, so the code fails rather than fall back. An event skipped by a deletion during the read is accepted as missing |
| 2026-11-15 | Events (`/issues/{n}/events` form), not the timeline API | The timeline's only unique data is `cross-referenced`, which embeds issues from other repos; it also repeats comments and reviews, and some of its items have no id |
| 2026-11-15 | An unchanged repo costs two requests per run (items and events), both 304s | ETags on the first page of each listing; the `since` of the items listing only moves when something changed |
| 2026-11-15 | Each run fetches events before items | Maintainer's choice: whether `/issues/events` pages back to the beginning of whatwg/html is the open question, and items take several runs |
| 2026-11-15 | Switch the test repo from whatwg/dom to whatwg/html; dom's data stays as fetched on 2026-11-14 | Maintainer's instruction: html is the biggest, so it's where GitHub's paging limits would show |

## Status

- Extractor (REST only, items by number, events from the repo-wide
  listing, all committed as JSON files, failing loudly when an assumption
  doesn't hold) and its tests are written. Tests run against an
  in-memory fake GitHub.
- whatwg/dom was fetched on 2026-11-14 by the previous design. It
  confirmed that `/issues/events` paged back to dom's first issue (150
  pages) and includes PR-only events (`review_requested`,
  `ready_for_review`). Its data stays; `config/repos.txt` now lists only
  whatwg/html.

## Next steps

1. Run the fetch workflow for whatwg/html until the backfill is done
   (several runs), and see whether the checks hold: whether
   `/issues/events` pages back to the beginning (known first: events are
   fetched before items), and whether every closed item has a `closed`
   event. Cross-check against the earlier prototype's
   figures (1,171 PRs and 2,167 issues in 2024–2026).
2. Decide what to do with whatwg/dom's data: refetch it with the new
   design, or keep it.
3. Check `config/repos.txt` against the list of Living Standards (whatwg/sg `db.json`), then all repos.
4. Daily job: GitHub Actions on a schedule, with a personal token as a
   secret (the built-in token's limit is too low for the backfill),
   committing to `data/github/` as the manual workflow does, and
   `--reconcile` weekly.
5. Then dashboards: bring back Maintenance load (commit `10edb66`),
   reworked around the prototype's catalog: PRs touched (split by size)
   instead of raw review counts, review sessions, sign-offs (`APPROVED` or
   LGTM), unquoted words.

## Dashboard ideas

- **Implementation follow-through:** for merged normative PRs, do the
  linked Chromium, Gecko and WebKit bugs get fixed, and how far does each
  engine lag? Needs the bug trackers (not approved).
- **Test coverage:** what share of normative PRs come with a WPT PR? The
  PR template's checkboxes are in the PR body already being fetched.
- **Backlog health:** open issues and PRs by age, and items stalled on
  labels like "needs implementer interest" or "agenda+". This can be built
  from the data already approved.
- **Value exchange:** each organization's share of maintenance against its
  engine's share of browser usage, as in cosh.
