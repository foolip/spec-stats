# Extraction: what is fetched and how updates work

Code: `specstats/extract.py` (fetching and storing), `specstats/github.py`
(the throttled client). Everything goes in `data/github/`, committed to
this repo, losslessly, as the API returned it, so any analysis can be
run offline, and rerun with new definitions at any time.

## Where it's stored

One pretty-printed JSON file (2-space indent, GitHub's field order, UTF-8,
trailing newline) per object or per item's list of objects, at a path
that mirrors the API path it comes from:

```
data/github/
  whatwg/dom/
    issues/1234.json            GET /repos/whatwg/dom/issues/1234 (issues and PRs)
    issues/1234/comments.json   conversation comments, sorted by id
    issues/1234/events.json     timeline events, sorted by id
    pulls/1234.json             GET /repos/whatwg/dom/pulls/1234 (PRs only)
    pulls/1234/reviews.json     reviews
    pulls/1234/comments.json    inline review comments, sorted by id
    pulls/1234/commits.json     (optional)
    pulls/1234/files.json       (optional)
    state.json                  cursors and ETags, which PR resources were fetched for
                                which updated_at, and numbers that are gone
  users/foolip.json             GET /users/foolip
```

Lists that would be empty have no file. Issues and PRs share one
`issues/` directory because they share one number sequence; a PR also
has `pulls/{n}.json`, the PR view of the same number.

Events from the repo-wide listing embed a copy of their issue as it was
when fetched; that copy is left out, so `events.json` holds what
`/issues/{n}/events` returns.

Query the files with `jq` or any JSON tool, e.g.
`jq -r '.[].user.login' data/github/whatwg/dom/issues/*/comments.json | sort | uniq -c | sort -n`.

**History is git's.** A changed object rewrites its file; a comment deleted
on GitHub is dropped from its list when refetched; a deleted or
transferred item has all its files removed. Every earlier version is in
`git log`. Unchanged objects re-read in the overlap don't change any file.

## What is fetched, per repo

| Stream or resource | What | Request | Incremental by |
|---|---|---|---|
| items | every issue and PR (labels, state, comment counts, reactions) | `GET /repos/{repo}/issues?state=all&sort=updated&direction=asc` | `since` |
| issue comments | every conversation comment on issues and PRs | `GET /repos/{repo}/issues/comments?sort=updated&direction=asc` | `since` |
| review comments | every inline review comment (`in_reply_to_id`, `path`, line, diff hunk, its review) | `GET /repos/{repo}/pulls/comments?sort=updated&direction=asc` | `since` |
| events | every timeline event: labeled, closed, merged, review requested, ready for review, converted to draft, assigned, … | `GET /repos/{repo}/issues/events` (newest first) | stop past the cursor |
| pull | per PR: merged_by, draft, size (additions, deletions, changed files), review comment count | `GET /repos/{repo}/pulls/{n}` | PRs whose `updated_at` changed |
| reviews | per PR: every review, with state and body | `GET /repos/{repo}/pulls/{n}/reviews` | same |
| commits | per PR, optional: commits, with author emails (at most 250 per PR) | `GET /repos/{repo}/pulls/{n}/commits` | same |
| files | per PR, optional: changed files with line counts (at most 3,000 per PR) | `GET /repos/{repo}/pulls/{n}/files` | same |
| users | public profiles: name, company, location | `GET /users/{login}` | logins not yet fetched |

REST has no repo-wide listing of reviews, commits or files, so those cost
requests per PR. Which per-PR resources are fetched is set in
`config/fetch.json`: `pull` and `reviews` by default, with `commits` and
`files` off until an analysis needs them. Each resource is tracked
separately (`fetched` in `state.json`), so turning one on later fetches just that
resource for every PR on the next run, without refetching anything else.

Bots and boilerplate are kept; analyses decide what counts.

Not fetched: diff patches, and anything outside GitHub (chat, meetings).
Deleted comments and items can't be fetched once they're gone, except as
the last version we stored.

## Building the mirror from nothing

There's no separate backfill mode, and no switch between orders. Every
listing is in order of `updated_at`, oldest first, and the first run is
just a run whose cursors start empty: it reads from the oldest-updated
item to the newest, and when it finishes, its cursor is "now". The next
run carries on from there with the same code.

Ordering by update rather than by creation is what makes this work:

- **Nothing changes behind the cursor unnoticed.** An item updated while
  the backfill runs gets a new `updated_at`, so it moves *ahead* of the
  cursor and is read again later in the same run, or by the next one. In
  creation order, an item already read could change and not be seen
  again, so a creation-order backfill would need a second, update-ordered
  pass to catch up afterwards.
- **Interruptions don't matter.** The cursor is saved per page, so a run
  that stops (a timeout, the rate limit) resumes where it was, however
  long the gap.
- **Per-PR resources follow the same rule:** they're fetched for every PR
  whose `updated_at` differs from the one they were fetched for, which on
  the first run is every PR.

Order per repo: the three ascending listings, then events, then per-PR
resources, then the count checks; then profiles for everyone seen. A
`reconcile` afterwards confirms that every issue number is accounted for.

## A run (`extract`)

For each repo:

1. **The three ascending listings** (items, issue comments, review
   comments) each start from their cursor (the newest `updated_at`
   stored) minus a **day of overlap**. So each run re-reads the last day,
   and anything an earlier run missed (identical timestamps, a briefly
   stale API, things that moved while we paged) is picked up.
   - The first page carries the ETag from the last run with the same
     `since`. If nothing changed, GitHub answers `304 Not Modified`, which
     doesn't count against the rate limit.
   - Pages are fetched by *keyset*: each next page is page 1 again, with
     `since` a second before the newest timestamp seen so far. Following
     page 2, 3, … links instead would skip a row whenever an item already
     read is updated mid-listing (it moves to the end, and the row after
     the page boundary slides back into the pages already read). Keyset
     pages can't skip, and never page deep enough to hit GitHub's
     pagination limit.
   - The cursor is saved after every page, so an interrupted run resumes
     where it stopped. Per-item fetches save `state.json` every 50 items.
2. **Events** are listed newest first until a day before the cursor. On
   the first run, if GitHub won't page back to the start of history, the
   oldest event reached is recorded as the *floor*, and items older than
   it get their events fetched one at a time (`/issues/{n}/events`).
3. **Per-PR resources:** for every PR whose `updated_at` differs from the
   one each resource was last fetched for. A PR's reviews (or commits, or
   files) are replaced as a set.
4. **Count checks:** every item's `comments` count is compared with the
   conversation comments stored for it, and every PR's `review_comments`
   count with the inline comments stored. Items that differ get their
   comments refetched one at a time. This needs no requests unless
   something differs.

A daily run of an unchanged repo is four requests, all 304s.

## Deadlines

`--max-minutes N` or `--stop-at <UTC time>` stops a run cleanly: no request
starts, and no rate-limit pause runs, past that point. A response is always
stored before the run stops, and `state.json` is saved, so the next run
continues where this one stopped:

- The ascending listings resume from their cursor, saved after every page.
- Per-PR and per-item fetches resume from `fetched` in `state.json`.
- The events listing is newest first and can't be resumed midway. A first
  run stopped during it records the oldest event reached as the *floor*,
  just as when GitHub stops paging, and older items get their events one
  at a time. A later run stopped during it simply re-reads from the newest.

Once caught up, a run needs at least four requests (one per stream), so
the deadline must allow more than that for a run to finish.

The workflow stops each run 300 minutes in, inside the job's 350-minute
limit, then commits. A backfill bigger than that takes several runs.

## The weekly reconcile (`reconcile`)

Issue and PR numbers are one sequence per repo, so completeness can be
checked exactly:

1. Re-list every item (about 120 pages for whatwg/html), storing any that
   changed.
2. Every number from 1 to the highest must then be either stored, or
   recorded as gone in `state.json`. Each number that's neither is fetched on its own:
   if it exists, it's stored (it had been missed); if GitHub says it was
   deleted, or it redirects to another repo (transferred), it's recorded
   as gone and not checked again. A stored item that turned out to be
   gone has its files removed.
3. If the numbers still don't add up, the command exits with an error.

The first reconcile after the backfill checks every number never seen, so
it costs one request per deleted or transferred issue; later ones only
check new gaps.

## Known gaps

- A comment deleted on an item that didn't otherwise change may not move
  the item's `updated_at`, so its count isn't rechecked. It stays stored
  until the item next changes.
- Untested against the real API (written in a session that couldn't reach
  it): how deep the repo-wide listings can page, and whether
  `/issues/events` includes PR-only events like `ready_for_review`. The
  first run on whatwg/dom settles both (`docs/plan.md`, next steps).
