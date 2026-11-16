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
   - Never wait for quota (since 2026-11-15): stop the run when the hourly
     budget is down to 500 requests (a tenth of a smaller budget), or on
     a 429 or secondary rate limit; the next run continues. 5xx and
     network errors are retried with back-off.
   - Incremental: fetch only what changed since the last run, by `since`
     and cursors (`docs/extraction.md`); no ETags (since 2026-11-16).
   - Identify ourselves: the User-Agent names the project and links the
     repo; the token says who is making the requests (no contact address
     since 2026-11-16).
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
| 2026-11-13 | ~~REST listings of whole repos (issues, comments, review comments, events)~~ (superseded on 2026-11-15: items by number, with their events), ~~plus batched GraphQL for reviews, commits and files~~ (superseded below: REST only) | REST supports `since` and ETags, so a daily run of an unchanged repo is four free 304s |
| 2026-11-13 | Re-read a day of overlap on every run, save cursors per page, ~~check comment counts per item~~, reconcile every number weekly, and ~~fail on count mismatches~~ (since 2026-11-15, consistency checks are separate from the fetch, below) (counts dropped on 2026-11-15: lists are refetched whole with their item, and whatwg/dom has items whose count never matches, e.g. #126, 43 vs 40) | Stopping at the last-seen item trusts the API to be perfect; these find and fill holes instead (`docs/extraction.md`) |
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
| 2026-11-15 | ~~**Events come only from the repo-wide `/issues/events` listing**, read back to the beginning once, then the new ones each run (a free 304 if none); no per-item event requests~~ (superseded the same day: per-item events, below). The run fails ~~if GitHub won't page back far enough, or~~ if a closed item has no `closed` event or a merged PR no `merged` event | Fewest requests (one per 100 events). It catches the events that don't move an item's `updated_at` (1,965 of 14,960 in whatwg/dom, mostly `referenced`). It paged back to 2012 for whatwg/dom; whatwg/html, the biggest, is the test, so the code fails rather than fall back. An event skipped by a deletion during the read is accepted as missing |
| 2026-11-15 | Events (`/issues/{n}/events` form), not the timeline API (confirmed by `timeline-check`, below) | The timeline's only unique data is `cross-referenced`, which embeds issues from other repos; it also repeats comments and reviews, and some of its items have no id |
| 2026-11-15 | An unchanged repo costs two requests per run (items and events), ~~both 304s~~ (no ETags since 2026-11-16, below) | ~~ETags on the first page of each listing;~~ the `since` of the items listing only moves when something changed |
| 2026-11-15 | ~~Each run fetches events before items~~ (reversed the same day: items first, as the events listing is only read after the items backfill) | Maintainer's choice: whether `/issues/events` pages back to the beginning of whatwg/html is the open question, and items take several runs |
| 2026-11-15 | ~~Switch the test repo from whatwg/dom to whatwg/html~~ (whatwg/fullscreen first, below); dom's data stays as fetched on 2026-11-14 | Maintainer's instruction: html is the biggest, so it's where GitHub's paging limits would show |
| 2026-11-15 | A read of `/issues/events` ~~(then the backfill)~~ that ends on a full page with no next link before reaching where it should fails the run | Run 4 (whatwg/html) showed GitHub ends the listing at page 300 silently, with no 422; the code took that as the beginning and went on to items, so the early check the events-first order was for didn't fire |
| 2026-11-15 | Test whether the timeline API (`/issues/{n}/timeline`, one listing per item) could replace the per-item comment, review and inline-comment requests and supply events older than the repo-wide listing's 300 pages: `timeline-check` compares it with whatwg/dom's stored data for a sample of items | Maintainer's question after whatwg/html's events were cut off. Timeline events are approved (ground rule 1). The earlier row choosing events over the timeline was about events alone; if the timeline holds everything, it could be fewer requests per item, not more |
| 2026-11-15 | **The timeline can't replace the per-item lists.** `timeline-check` on 40 whatwg/dom items: issue comments all there and identical; reviews 92 of 386 (none of the 294 that only reply in an existing thread, and `state`, `user` and `body` differ); inline comments 43 of 576 (only those not part of a review); events 1,613 of 1,801 (188 missing, mostly `referenced`, `subscribed` and `mentioned`, no rule found). The endpoint's only parameters are paging and `exclude`. Details in `docs/extraction.md` | Only the comments request could go, at the cost of a timeline request per item. Cross-references are the one thing only the timeline has: a reason to add it later (as an optional per-item resource, with `exclude` to keep it small) if a dashboard needs them, e.g. WPT PRs linking to spec PRs; adding it later costs the same requests as now |
| 2026-11-15 | Test on whatwg/fullscreen before whatwg/html | Maintainer's instruction: see whether the extractor works end to end at all. With about 260 issues and PRs (roughly 1,000 requests), one run does the whole backfill, the first read of the events listing and the checks |
| 2026-11-15 | **The fetch stores what GitHub returns, consistent or not; consistency checks run separately** (`specstats check`, offline, in its own workflow, `check.yml`, triggered manually for now; not in the fetch workflow or triggered by it, at the maintainer's instruction). The fetch fails only when fetching can't be done right (the events listing won't reach back far enough, or `config/fetch.json` changed). The checks: every number reached is stored or gone, closed items have a `closed` event, merged PRs a `merged` event, PRs a `pulls/{n}/index.json`, no events under numbers neither stored nor gone | Maintainer's choice: GitHub's data isn't perfectly consistent (whatwg/fullscreen #220, a probable spam PR closed by its author, has no events at all, not even `closed`), so failing the fetch on it stops collection for no fault of ours. The checks are for finding bugs in the end-to-end process; a finding may turn out to be GitHub's |
| 2026-11-15 | The fetch workflow uses the built-in token; no personal token. Each run logs the rate limit GitHub reports. ETags don't save requests there | Maintainer's choice. The built-in token has had 5,000 requests an hour (run 4 stopped at the 500 reserve, about every 4,500 requests; run 5 made 1,017), not the 1,000 the docs said. It's new every run and GitHub's ETags are per token (`Vary: Authorization`; same token: stable ETag and a 304 after 70 s), so runs 6 and 7 of an unchanged whatwg/fullscreen got 200s with new ETags. That costs two requests per run |
| 2026-11-16 | Fetch whatwg/dom again, by the current design, alongside whatwg/fullscreen: its old-format `state.json` is removed (so the backfill starts from #1), its files are kept and replaced number by number | Maintainer's instruction. Each number's files are replaced whole when the backfill reaches it (deleted and transferred numbers, 81 of them with only events stored, are removed), so nothing needs deleting first, and git shows how the two designs' data differ |
| 2026-11-16 | **No ETags**: no conditional requests, and none stored in `state.json` (removed from whatwg/fullscreen's and whatwg/dom's) | Maintainer's instruction. With the built-in token they never matched, and saving the new ones made every run of an unchanged repo commit a changed `state.json` (runs 6–8). With a stable token they'd save at most two requests per run per repo; `since` and the cursors are what keep runs small |
| 2026-11-16 | The workflows no longer read a `SPECSTATS_TOKEN` secret; they use only the built-in token | Maintainer's instruction. The secret was never set, and the built-in token's 5,000 an hour is enough |
| 2026-11-16 | No contact address in the User-Agent: `SPECSTATS_CONTACT` and `data/private/settings.json` removed | Maintainer's instruction. Every request is authenticated, so GitHub already knows who is making it (the repo's Actions installation, or the operator's own token), and its docs only ask for a username or app name in the User-Agent |
| 2026-11-15 | **Events are fetched per item** (`GET /issues/{n}/events` with everything else for the number, every item); the repo-wide `/issues/events` listing is read only after the items backfill, from a day before the backfill started, then back to the last run's newest event | Maintainer's choice. GitHub ends the repo-wide listing after 300 pages, so it can't be the backfill for whatwg/html; per item, a backfilled number is complete with its events. Costs one request per item more (about 11,000 for whatwg/html). The listing still catches the events that don't move an item's `updated_at` |
| 2026-11-15 | A run never waits for rate-limit quota: at the hourly reserve, or on a 429, secondary or primary rate limit, it stops cleanly as at its deadline (`RateLimited`), and the next run continues | Maintainer's instruction: the runner mustn't idle. Run 4 spent about 3¼ of its 4⅓ hours paused for the reset |
| 2026-11-15 | If main moved during a fetch run, the run fails without committing its data (it was rebased onto the new main) | Maintainer's choice: the collection code may have changed under the run. Run 4's rebase failed anyway, for want of a git identity |

## Status

- Extractor (REST only, items by number with their events, then the
  repo-wide events listing for updates, all committed as JSON files,
  failing loudly when an assumption doesn't hold) and its tests are
  written. Tests run against an
  in-memory fake GitHub.
- Run 4 (2026-11-15, whatwg/html) made 22,504 requests in 4h22m, the
  full 5,000-an-hour budget: each hour's budget went in about 20 minutes
  and the rest was a rate-limit pause. `/issues/events` stopped at page
  300 (back to 2024-12-06) with no error, and the commit step failed
  (main had moved), so nothing from it was kept. Since then: runs
  stop instead of waiting for quota, a run during which main moves
  fails on purpose, and events are fetched per item.
- whatwg/dom was fetched on 2026-11-14 by the previous design. It
  confirmed that `/issues/events` paged back to dom's first issue (150
  pages) and includes PR-only events (`review_requested`,
  `ready_for_review`). It's being refetched by the current design
  (2026-11-16); `config/repos.txt` lists whatwg/fullscreen and whatwg/dom.
- Run 5 (2026-11-15) fetched whatwg/fullscreen whole in one run: 1,017
  requests in about 6 minutes; numbers 1–265, 259 stored (122 issues and
  137 PRs, as GitHub's search counts) and 6 gone. The only
  inconsistency: #220, a closed PR with no events at all, which then
  failed the run; the checks are now separate (decisions log).

## Next steps

1. Run the fetch for whatwg/dom's backfill (about 1,530 numbers, roughly
   5,500 requests: two runs, an hour apart), then "Check data" by hand,
   and look at the git diff against the 2026-11-14 data. (Run 9 of an
   unchanged whatwg/fullscreen: two requests, no commit.)
2. Then switch to whatwg/html and run the fetch workflow until the
   backfill is done (about one run per hour of budget, at roughly 4
   requests per item), look at what "Check data" finds, and cross-check
   against the earlier prototype's figures (1,171 PRs and 2,167 issues in
   2024–2026).
3. Check `config/repos.txt` against the list of Living Standards (whatwg/sg `db.json`), then all repos.
4. Daily job: GitHub Actions on a schedule, with the built-in token,
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
