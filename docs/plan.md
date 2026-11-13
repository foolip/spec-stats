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
   API for the WHATWG repos in `config/repos.txt` (PRs, issues, reviews,
   comments, and the public profiles of accounts seen in them). Not
   approved yet: git clones, browser bug trackers, wpt.fyi, and any repo
   outside `whatwg/`.
   - `extract` and `users` print a plan unless given `--go`.
2. **Be gentle with GitHub.**
   - Serial requests, at least 1 s apart (`github.MIN_INTERVAL`).
   - Back off on 403/429/5xx and secondary rate limits, honoring
     `Retry-After`; pause when the hourly GraphQL budget drops below 500 points.
   - Incremental: list newest-updated first and stop at the first unchanged item.
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
| 2026-11-13 | GraphQL, not REST: one query gets a page of PRs with their reviews and comments | Far fewer requests; nested connections that don't fit are completed with follow-up queries |
| 2026-11-13 | Raw cache keeps the whole GraphQL node per PR or issue, keyed by (repo, kind, number), replaced when `updatedAt` changes | Lossless and rebuildable; derive runs offline |
| 2026-11-13 | Count each action in the month it happened (review submitted, comment written, merge), not when the PR closed | Same lesson as cosh's metric_version 3: close-week counting smears long-running PRs |
| 2026-11-13 | Org from the profile `company` field plus `config/affiliations.json` overrides | The WHATWG has no affiliations file like Chromium's; `company` is public and self-declared |
| 2026-11-13 | Self-reviews and bots are left out; the PR author's comments aren't "responses" | Replies in one's own review threads are recorded as reviews, but they aren't review work |
| 2026-11-13 | Web pages are plain HTML, CSS and ES modules, with no build step | Small enough not to need one |

## Status

- Extractor, derive, summarize, tests and the Maintenance load page are written.
- The page has been checked against synthetic data only, in light, dark
  and phone layouts.
- **Nothing has been fetched yet.** The first run needs a GitHub token on
  the maintainer's machine (the cloud session that wrote this couldn't
  reach the WHATWG repos through the API).

## Next steps

1. Check `config/repos.txt` against the list of Living Standards (whatwg/sg `db.json`).
2. First fetch: `extract --repo whatwg/dom --go` to measure requests and
   cost, then all repos, then `users --go`.
3. Look at how big `Unknown` is, and fill `config/affiliations.json` with
   publicly sourced entries for the most active accounts.
4. Confirm ground rule 3, then commit the first real summaries.
5. Publish the site with GitHub Pages (serve the repo root so
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
