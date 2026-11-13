# Extraction: what is fetched and how updates work

Code: `specstats/extract.py` (fetching and storing), `specstats/github.py`
(the throttled client). Everything goes in `data/private/raw.sqlite`,
losslessly, as the API returned it, so derive and summarize can be rerun
offline with new definitions at any time.

## What is fetched, per repo

Everything comes from the REST API, and every object is stored as plain
JSON text with all the fields GitHub returned, so the database can be
queried directly:

```sql
SELECT json_pretty(json) FROM items WHERE repo = 'whatwg/dom' AND number = 1234;
SELECT json_extract(json, '$.user.login'), COUNT(*) FROM issue_comments GROUP BY 1 ORDER BY 2 DESC;
```

Each table also has a few columns for lookups (repo, number, `id`,
`node_id`, the object's timestamp).

| Table | What | Request | Incremental by |
|---|---|---|---|
| `items` | every issue and PR (labels, state, comment counts, reactions) | `GET /repos/{repo}/issues?state=all&sort=updated&direction=asc` | `since` |
| `issue_comments` | every conversation comment on issues and PRs | `GET /repos/{repo}/issues/comments?sort=updated&direction=asc` | `since` |
| `review_comments` | every inline review comment (`in_reply_to_id`, `path`, line, diff hunk, its review) | `GET /repos/{repo}/pulls/comments?sort=updated&direction=asc` | `since` |
| `events` | every timeline event: labeled, closed, merged, review requested, ready for review, converted to draft, assigned, … | `GET /repos/{repo}/issues/events` (newest first) | stop past the cursor |
| `pulls` | per PR: merged_by, draft, size (additions, deletions, changed files), review comment count | `GET /repos/{repo}/pulls/{n}` | PRs whose `updated_at` changed |
| `pr_reviews` | per PR: every review, with state and body | `GET /repos/{repo}/pulls/{n}/reviews` | same |
| `pr_commits` | per PR, optional: commits, with author emails (at most 250 per PR) | `GET /repos/{repo}/pulls/{n}/commits` | same |
| `pr_files` | per PR, optional: changed files with line counts (at most 3,000 per PR) | `GET /repos/{repo}/pulls/{n}/files` | same |
| `users` | public profiles: name, company, location | `GET /users/{login}` | logins not yet fetched |

REST has no repo-wide listing of reviews, commits or files, so those cost
requests per PR. Which per-PR resources are fetched is set in
`config/fetch.json`: `pull` and `reviews` by default, with `commits` and
`files` off until an analysis needs them. Each resource is tracked
separately (`pr_fetched`), so turning one on later fetches just that
resource for every PR on the next run, without refetching anything else.

Bots and boilerplate are kept here; derive decides what counts.

**History.** When a stored object changes (its `updated_at` moves, or, for
objects without one such as reviews and files, its JSON changes), the
previous version goes in `history` with the time we saw the new one. Edited
comments, changed labels on an item and profile `company` changes over
time are all kept. Objects that disappeared on refetch (a deleted comment,
a deleted issue) go there too, marked `removed`. Unchanged objects re-read
in the overlap add nothing.

Not fetched: diff patches, and anything outside GitHub (chat, meetings).
Deleted comments and items can't be fetched once they're gone, except as
the last version we stored.

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
   - The cursor is saved after every page, so an interrupted run resumes
     where it stopped.
   - If GitHub refuses to page that deep (HTTP 422), the listing restarts
     with `since` set to the newest timestamp reached.
2. **Events** are listed newest first until a day before the cursor. On
   the first run, if GitHub won't page back to the start of history, the
   oldest event reached is recorded as the *floor*, and items older than
   it get their events fetched one at a time (`/issues/{n}/events`).
3. **Per-PR resources:** for every PR whose `updated_at` differs from the
   one each resource was last fetched for. A PR's reviews (or commits, or
   files) are replaced as a set; ones no longer there move to history.
4. **Count checks:** every item's `comments` count is compared with the
   conversation comments stored for it, and every PR's `review_comments`
   count with the inline comments stored. Items that differ get their
   comments refetched one at a time. This needs no requests unless
   something differs.

A daily run of an unchanged repo is four requests, all 304s.

## The weekly reconcile (`reconcile`)

Issue and PR numbers are one sequence per repo, so completeness can be
checked exactly:

1. Re-list every item (about 120 pages for whatwg/html), storing any that
   changed.
2. Every number from 1 to the highest must then be either stored, or
   recorded in `gone`. Each number that's neither is fetched on its own:
   if it exists, it's stored (it had been missed); if GitHub says it was
   deleted, or it redirects to another repo (transferred), it's recorded
   in `gone` and not checked again. A stored item that turned out to be
   gone moves to history.
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
