# Extraction: what is fetched and how updates work

Code: `specstats/extract.py` (fetching and storing), `specstats/github.py`
(the throttled client). Everything goes in `data/private/raw.sqlite`,
losslessly, as the API returned it, so derive and summarize can be rerun
offline with new definitions at any time.

## What is fetched, per repo

| Table | Source | Request | Incremental by |
|---|---|---|---|
| `items` | every issue and PR (REST issue objects, with labels, state, comment counts, reactions) | `GET /repos/{repo}/issues?state=all&sort=updated&direction=asc` | `since` |
| `issue_comments` | every conversation comment on issues and PRs | `GET /repos/{repo}/issues/comments?sort=updated&direction=asc` | `since` |
| `review_comments` | every inline review comment, with `in_reply_to_id`, `path`, line and its review | `GET /repos/{repo}/pulls/comments?sort=updated&direction=asc` | `since` |
| `events` | every timeline event: labeled, closed, merged, review requested, ready for review, converted to draft, assigned, … | `GET /repos/{repo}/issues/events` (newest first) | stop past the cursor |
| `pr_details` | per PR: reviews (with bodies), commits (with author emails and parent counts), changed files (with line counts) | batched GraphQL, 20 PRs per query | PRs whose `updated_at` changed |
| `users` | public profiles: name, company, location | batched GraphQL, 50 per query | logins not yet fetched |

All listings ask for 100 per page. Bots and boilerplate are kept here;
derive decides what counts.

Not fetched: edit histories of comments, diff hunks and patches, and
anything outside GitHub (chat, meetings). Deleted comments and items can't
be fetched at all.

## A run (`extract`)

For each repo:

1. **The three ascending listings** (items, issue comments, review
   comments) each start from their cursor (the newest `updated_at`
   stored) minus a **day of overlap**. So each run re-reads the last day,
   and anything an earlier run missed (identical timestamps, a briefly
   stale API, things that moved while we paged) is picked up. Re-storing
   an unchanged row is harmless.
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
3. **PR details:** every PR whose `updated_at` differs from the one its
   stored details were fetched for is refetched in batched GraphQL.
   Nested connections that don't fit (more than 100 reviews, commits or
   files) are completed with follow-up queries. A PR's details are
   replaced as a whole, never patched.
4. **Count checks:** every item's comment count (from GitHub) is compared
   with the comments stored for it, and every PR's review comment count
   (the sum over its reviews) with the review comments stored. Items that
   differ get their comments refetched one at a time, which also drops
   comments that were deleted. This needs no requests unless something
   differs.

A daily run of an unchanged repo is four requests, all 304s.

## The weekly reconcile (`reconcile`)

Lists every issue and PR number with its `updatedAt` (GraphQL, numbers
only, 100 per page: about 110 pages for whatwg/html) and compares with
what's stored:

- missing or older here: refetched;
- here but not on GitHub: checked one by one, and marked `deleted` or
  `transferred`, which derive leaves out;
- the totals must then match exactly, or the command exits with an error,
  so a hole is noticed rather than silently kept.

## Known gaps

- A comment deleted on an item that didn't otherwise change may not move
  the item's `updated_at`, so its count isn't rechecked. It stays in the
  raw cache until the item next changes. The effect on metrics is small,
  and the raw cache is private.
- Untested against the real API (written in a session that couldn't reach
  it): how deep the repo-wide listings can page, and whether
  `/issues/events` includes PR-only events like `ready_for_review`. The
  first run on whatwg/dom settles both (`docs/plan.md`, next steps).
