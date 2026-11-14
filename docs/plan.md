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
   - `extract`, `reconcile` and `users` are dry runs that print a plan;
     they fetch only when given `--go`.
2. **Be gentle with GitHub.**
   - Serial requests, at least 1 s apart (`github.MIN_INTERVAL`).
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
| 2026-11-13 | REST listings of whole repos (issues, comments, review comments, events), ~~plus batched GraphQL for reviews, commits and files~~ (superseded below: REST only) | REST supports `since` and ETags, so a daily run of an unchanged repo is four free 304s |
| 2026-11-13 | Re-read a day of overlap on every run, save cursors per page, check comment counts per item, reconcile every number weekly, and fail on count mismatches | Stopping at the last-seen item trusts the API to be perfect; these find and fill holes instead (`docs/extraction.md`) |
| 2026-11-13 | **REST only**, no GraphQL: per-PR requests for reviews instead of batched queries | REST returns whole objects, so everything is stored without maintaining field lists; one representation, ETags and `since` throughout. Costs a longer one-time backfill (roughly 2 requests per PR) |
| 2026-11-13 | Per-PR commits and files are optional (`config/fetch.json`), off for now | Not sure they're needed; each resource is tracked separately, so turning one on later fetches only that |
| 2026-11-13 | Raw objects are stored as plain JSON text, uncompressed (in files since 2026-11-14) | The maintainer wants to query the database and see the JSON directly. A few GB is fine |
| 2026-11-13 | Keep previous versions of changed objects (~~`history`~~ git, since 2026-11-14) | Edits, label changes and profile changes are otherwise lost; future analyses may want them, and it's cheap |
| 2026-11-13 | Reconcile by issue number: every number from 1 to the highest is stored or recorded as deleted/transferred | Numbers are one sequence per repo, so completeness can be checked exactly |
| 2026-11-14 | Page listings by keyset (`since` just before the newest row seen), not offset links | An offset page skips a row whenever an already-read item is updated mid-listing; that would happen during a long backfill. Also avoids GitHub's deep-pagination limit |
| 2026-11-14 | Start with whatwg/dom only, fetched by a manually triggered GitHub Actions workflow; ~~the raw cache is kept as a workflow artifact (90 days)~~ the data is committed (below) | Maintainer's instruction: populate and check one repo first |
| 2026-11-13 | PR diffs and git history deferred | Spec text written is interesting, but needs git (API patches are truncated for large PRs); API data first |
| 2026-11-13 | Response time counts from ready-for-review for PRs opened as drafts, and "unanswered" means no response within 7 days | From the earlier whatwg/html prototype: responses during a draft aren't triage, and a median alone hides items nobody answers |
| 2026-11-13 | Merges are split into self and other; generated boilerplate comments are left out | Same prototype: a self-merge isn't review work, and PR preview comments aren't comments |
| 2026-11-13 | Count each action in the month it happened (review submitted, comment written, merge), not when the PR closed | Same lesson as cosh's metric_version 3: close-week counting smears long-running PRs |
| 2026-11-13 | Org from the profile `company` field plus `config/affiliations.json` overrides | The WHATWG has no affiliations file like Chromium's; `company` is public and self-declared |
| 2026-11-13 | Self-reviews and bots are left out; the PR author's comments aren't "responses" | Replies in one's own review threads are recorded as reviews, but they aren't review work |
| 2026-11-13 | Web pages are plain HTML, CSS and ES modules, with no build step | Small enough not to need one |
| 2026-11-14 | Stay with Python (standard library only), with our own small REST client rather than a wrapper library | Maintainer's choice. The extractor needs raw JSON, ETags, `since` with overlap and per-page cursors, which wrappers hide or don't help with; Octokit's throttling plugin (TypeScript) was the main thing given up |
| 2026-11-14 | Issues and PRs (the `/issues` listing) are committed to this repo, one file per item: `data/github/{owner}/{repo}/issues/{number}.json`, pretty-printed (2-space indent, GitHub's field order, trailing newline). ~~SQLite stays the working cache~~ (superseded below) | Maintainer's choice. A file per item keeps each update a small diff and every file small; git keeps the history and hosts the data long term, and a run can resume from the files if the artifact is gone. One directory for both kinds, as they share one number sequence |
| 2026-11-14 | **No SQLite for raw data.** Everything fetched is committed as files laid out like the API paths (`issues/{n}.json`, `issues/{n}/comments.json`, `pulls/{n}/reviews.json`, `users/{login}.json`, …) plus a `state.json` per repo; git replaces the `history` table and the workflow artifact. Events are stored without their embedded copy of the issue. SQLite may come back for crunching | Maintainer's choice: public, browsable data in one place with its history, and no second copy to keep in sync. The embedded issue is a snapshot of `issues/{n}.json` at fetch time, repeated on every event |
| 2026-11-14 | The fetch workflow only fetches and commits; it doesn't run `derive` or `summarize` | Maintainer's instruction: the raw data isn't to be summarized yet. ~~The code stays for later~~ removed (next row) |
| 2026-11-14 | Removed `derive`, `summarize`, org attribution (`orgs.py`, `config/affiliations.json`, `companies.json`, `bots.txt`), `summaries/`, `web/` and `docs/maintenance-load.md`; last version at `10edb66` | Maintainer's instruction: collect data first; the dashboard will be reworked anyway (next steps) |

## Status

- Extractor (REST only, incremental, storing everything as committed JSON
  files, with consistency checks and `reconcile`) and its tests are
  written. Tests run against an in-memory fake GitHub.
- **Nothing has been fetched yet.** The first run needs a GitHub token on
  the maintainer's machine (the cloud session that wrote this couldn't
  reach the WHATWG repos through the API).

## Next steps

1. Check `config/repos.txt` against the list of Living Standards (whatwg/sg `db.json`).
2. First fetch: `extract --repo whatwg/dom --go` to measure requests and
   cost, and to confirm two things the code assumes but couldn't test:
   how deep GitHub lets the repo-wide listings page (the code falls back if
   not deep enough), and that `/issues/events` includes PR-only events
   (`ready_for_review`, `review_requested`). Then whatwg/html, cross-checked
   against the figures of the earlier prototype (1,171 PRs and 2,167 issues
   in 2024–2026), then all repos, then `users --go`.
3. Daily job: GitHub Actions on a schedule, with a personal token as a
   secret (the built-in token's limit is too low for the backfill),
   committing to `data/github/` as the manual workflow does.
4. Then dashboards: bring back Maintenance load (commit `10edb66`),
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
