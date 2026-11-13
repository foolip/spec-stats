# spec-stats plan, decisions and status

This is the entry point for anyone (a person or a fresh Claude session)
picking the project up. Read this, then `README.md`, then
`docs/maintenance-load.md`.

## Goal

A set of dashboards about the health of WHATWG spec maintenance, published
as one static site: a landing page (`web/index.html`) with a card per
dashboard. Each dashboard answers one question from public data. Each data
source gets its own extractor, a raw cache in `data/private/` kept
losslessly, and small committed summaries that the pages read.

### First dashboard: Maintenance load (`web/maintenance.html`)

Who reviews, merges and triages changes to each Living Standard, by
organization over time; how few people carry each spec (people doing 50% of
reviews and merges in the last 12 months); and how long issues and PRs wait
for a first response. Definitions: `docs/maintenance-load.md`.

## Ground rules

1. **Fetch only what has been approved.** Approved on 2026-11-13: the GitHub
   REST API for the WHATWG repos in `config/repos.txt`: all activity on
   their issues and PRs (comments, inline review comments, timeline events,
   reviews, commits, changed files) and the public profiles of accounts
   seen in them. Not approved: git clones (deferred on 2026-11-13: API data
   first), browser bug trackers, wpt.fyi, GH Archive, and any repo outside
   `whatwg/`.
   - `extract` and `users` print a plan unless given `--go`.
2. **Be gentle with GitHub.**
   - Serial requests, at least 1 s apart (`github.MIN_INTERVAL`).
   - Back off on 429/5xx and secondary rate limits, honoring
     `Retry-After`; pause when the hourly budget drops below 500 requests.
   - Incremental: fetch only what changed since the last run, with ETags so
     unchanged listings are free 304s (`docs/extraction.md`).
   - Identify ourselves: the User-Agent carries the operator's contact
     address from the gitignored `data/private/settings.json`.
3. **Publishing per-person data.** Proposed: reviews, merges, names, logins
   and profile companies are already public on GitHub, so per-person counts
   may go in `summaries/` and on the site, as cosh does (its ground rule 3).
   **This needs the maintainer's confirmation before the first real
   summaries are committed.** Affiliations that aren't backed by a public
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
| 2026-11-13 | Raw objects are stored as plain JSON text, uncompressed | The maintainer wants to query the database and see the JSON directly. A few GB is fine |
| 2026-11-13 | Keep previous versions of changed objects (`history`) | Edits, label changes and profile changes are otherwise lost; future analyses may want them, and it's cheap |
| 2026-11-13 | Reconcile by issue number: every number from 1 to the highest is stored or recorded as deleted/transferred | Numbers are one sequence per repo, so completeness can be checked exactly |
| 2026-11-13 | PR diffs and git history deferred | Spec text written is interesting, but needs git (API patches are truncated for large PRs); API data first |
| 2026-11-13 | Response time counts from ready-for-review for PRs opened as drafts, and "unanswered" means no response within 7 days | From the earlier whatwg/html prototype: responses during a draft aren't triage, and a median alone hides items nobody answers |
| 2026-11-13 | Merges are split into self and other; generated boilerplate comments are left out | Same prototype: a self-merge isn't review work, and PR preview comments aren't comments |
| 2026-11-13 | Count each action in the month it happened (review submitted, comment written, merge), not when the PR closed | Same lesson as cosh's metric_version 3: close-week counting smears long-running PRs |
| 2026-11-13 | Org from the profile `company` field plus `config/affiliations.json` overrides | The WHATWG has no affiliations file like Chromium's; `company` is public and self-declared |
| 2026-11-13 | Self-reviews and bots are left out; the PR author's comments aren't "responses" | Replies in one's own review threads are recorded as reviews, but they aren't review work |
| 2026-11-13 | Web pages are plain HTML, CSS and ES modules, with no build step | Small enough not to need one |

## Status

- Extractor (REST only, incremental, with version history, consistency
  checks and `reconcile`), derive, summarize, tests and the Maintenance load page are
  written. Tests run against an in-memory fake GitHub.
- The page has been checked against synthetic data only, in light, dark
  and phone layouts.
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
   in 2024–2026; 41.3% of 2026's reviews by the PR's author), then all
   repos, then `users --go`.
3. Rework the metrics around the prototype's catalog: PRs touched (split
   by size) instead of raw review counts, review sessions, sign-offs
   (`APPROVED` or LGTM), unquoted words.
4. Daily job: GitHub Actions on a schedule, with a personal token as a
   secret (the built-in token's limit is too low for the backfill) and the
   raw cache in private storage (R2 proposed; not decided).
5. Look at how big `Unknown` is, and fill `config/affiliations.json` with
   publicly sourced entries for the most active accounts.
6. Confirm ground rule 3, then commit the first real summaries.
7. Publish the site with GitHub Pages (serve the repo root so
   `web/` can read `summaries/`).

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
