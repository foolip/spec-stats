# Extraction: what is fetched and how updates work

Code: `specstats/extract.py` (fetching and storing), `specstats/github.py`
(the serial client). Everything goes in `data/github/`, committed to
this repo, losslessly, as the API returned it, so any analysis can be
run offline, and rerun with new definitions at any time.

The design goal (2026-11-15) is the simplest approach that's complete as
it goes: fetch one issue or PR number at a time, and check assumptions
about GitHub's data by failing loudly rather than working around them.

## Where it's stored

One pretty-printed JSON file (2-space indent, GitHub's field order, UTF-8,
trailing newline) per object or per item's list of objects, at a path
that mirrors the API path it comes from:

```
data/github/
  whatwg/html/
    issues/1234/index.json      GET /repos/whatwg/html/issues/1234 (issues and PRs)
    issues/1234/comments.json   GET …/issues/1234/comments
    issues/1234/events.json     this item's events from GET …/issues/events, sorted by id
    pulls/1234/index.json       GET …/pulls/1234 (PRs only)
    pulls/1234/reviews.json     GET …/pulls/1234/reviews
    pulls/1234/comments.json    GET …/pulls/1234/comments (inline review comments)
    pulls/1234/commits.json     (optional)
    pulls/1234/files.json       (optional)
    state.json                  how far each part has got, and numbers that are gone
```

Lists that would be empty have no file. Issues and PRs share one
`issues/` directory because they share one number sequence; a PR also
has `pulls/{n}/index.json`, the PR view of the same number.

Events from the repo-wide listing embed a copy of their issue as it was
when fetched; that copy is left out, so `events.json` holds what
`/issues/{n}/events` would return.

Query the files with `jq` or any JSON tool, e.g.
`jq -r '.[].user.login' data/github/whatwg/html/issues/*/comments.json | sort | uniq -c | sort -n`.

**History is git's.** A changed object rewrites its file; a comment deleted
on GitHub is gone from its list when the item is next fetched; a deleted
or transferred item has all its files removed. Every earlier version is
in `git log`.

whatwg/dom was fetched on 2026-11-14 by the earlier design (repo-wide
listings of comments and review comments, merged by id); its files are
in the same layout, but its `state.json` is in the old format and it
isn't updated for now.

## One item: `sync_item(n)`

Everything for one number is fetched together and replaces what's stored:

| Request | When |
|---|---|
| `GET /issues/{n}` | always |
| `GET /issues/{n}/comments` | if the issue's `comments` count isn't 0 |
| `GET /pulls/{n}` | PRs, if `pull` is in `config/fetch.json` (default) |
| `GET /pulls/{n}/reviews` | PRs, if `reviews` is in `config/fetch.json` (default) |
| `GET /pulls/{n}/commits`, `/files` | PRs, if turned on in `config/fetch.json` (off) |
| `GET /pulls/{n}/comments` | PRs, unless `pull` says `review_comments` is 0 |

So an issue costs one or two requests and a PR three to five, plus one
per extra page of a long list. `index.json` is written last: its
`updated_at` is what says the item is synced, so a run stopped midway
fetches the item again.

If `GET /issues/{n}` answers 404 or 410 (deleted, never existed, or a
discussion), or redirects (transferred to another repo), the number is
recorded as gone in `state.json`, anything stored for it is removed, and it
isn't fetched again. **Redirects aren't followed**, so nothing is
fetched from the other repo; a transfer is treated as a deletion.

The set of per-PR resources is recorded in `state.json`. Changing it in
`config/fetch.json` makes the run fail: fetching a newly enabled
resource for every existing PR isn't implemented yet.

## Items: backfill by number, then updates

**Backfill.** Find the highest number, then `sync_item` every number from
1 to it. The cursor is just the next number (`items.next` in
`state.json`), so a run can stop between any two items and the next run
continues there, and every number below the cursor is stored or gone.

The highest number is that of the newest-created item, or higher if an
issue was transferred in since: a transferred issue keeps its creation
date but gets the next number (whatwg/dom #1340 is one). A transfer
moves `updated_at`, so the highest number is the most of the newest-created
item and the items updated since it was created.

**Updates.** Each later run lists
`GET /issues?state=all&sort=updated&direction=asc&since=S` and syncs each
listed item whose `updated_at` differs from the stored one. `S` is the
newest `updated_at` seen, minus a day of overlap, so anything a run
missed (identical timestamps, a briefly stale API) is listed again. After
the backfill, the cursor starts at the time the backfill started, so
everything that changed during it is fetched again.

- The first page carries the ETag from the last run with the same
  `since`. `S` only moves when something changed, so **an unchanged repo
  is one request, a `304 Not Modified`**, which doesn't count against
  the rate limit.
- A listed number above the highest known one (new issues, transfers in)
  first syncs every number in between, so deleted ones are recorded as
  gone, and the "every number below is stored or gone" rule keeps
  holding.
- Pages are fetched by *keyset*: each next page is page 1 again, with
  `since` a second before the newest timestamp seen. Following page 2,
  3, … links instead would skip a row whenever an item already read is
  updated mid-listing. The cursor is saved after every page.

This relies on every change to an item's comments, reviews or inline
comments also moving the item's `updated_at`. In whatwg/dom's data that
held for every comment (including 2,146 edited ones), review and inline
comment.

## Events: the repo-wide listing only

Events come only from `GET /issues/events` (newest first), never from
per-item requests:

- **Backfill:** read the listing back to the beginning, by page number,
  saving the page after each one. New events during the backfill push
  rows onto later pages, where they're read again (merged by id), so
  resuming days later is safe. A deletion during it can skip one event
  per page boundary; that's accepted.
- **Updates:** read page 1 with its ETag (a free 304 if there's nothing
  new), and on back to a day before the newest event seen.
- Events of numbers recorded as gone are dropped: the listing keeps
  events of deleted and transferred issues (whatwg/dom had 81 such
  numbers).

This catches events that don't move the item's `updated_at`. In
whatwg/dom that's 1,965 of 14,960 events: mostly `referenced`,
`subscribed` and `mentioned`, and `head_ref_deleted`.

It also **assumes GitHub pages the listing all the way back**. That held
for whatwg/dom (150 pages, back to its first issue in 2012), but **not for
whatwg/html**: on 2026-11-15 its listing ended at page 300 (30,000
events, back to 2024-12-06), a full page with no next link and no error.
The run now fails there (below) rather than fall back to per-item event
requests; how to get older events is undecided (`docs/plan.md`).

## Checks (`CheckFailed`)

A run stores what it fetched, then exits with an error if an assumption
doesn't hold:

- GitHub refuses to page `/issues/events` back to the beginning
  (HTTP 422), or back to the last run's events, or the backfill's last
  page is full (100 events) with no next link, which is how GitHub cut
  off whatwg/html's listing at page 300. A listing that really ends on
  a full page fails too; that's the safe side.
- Once both backfills are done, on every run: every closed item has a
  `closed` event, every merged PR has a `merged` event, and no events
  are stored for a number up to the highest that's neither stored nor
  gone. A listing cut off on a short page would show up here.
- With `--reconcile`, every number up to the highest is stored or gone.
- `config/fetch.json` changed its per-PR resources.

## A run (`extract`)

Per repo: events (backfill or update), then the items backfill or an
update, then with `--reconcile` the reconcile, then the checks once both
backfills are done. Events go first so that whether GitHub pages them all
the way back is known before the much longer items backfill. Events
filed under a number that turns out to be gone are removed when the
items backfill reaches it.

A caught-up run of an unchanged repo is two requests, both free 304s.

## Deadlines

`--max-minutes N` stops a run cleanly: no request starts, and no
rate-limit pause runs, after N minutes. The items backfill continues from
`items.next`, item updates from the cursor saved per page, and the events
backfill from its saved page. An events update stopped midway saves
nothing and re-reads from the newest next time.

The smallest unit of work is one PR: three to five requests, more for very
long lists. Once the events backfill is done, every run also spends one
request on events first.

The workflow stops each run 300 minutes in, inside the job's 350-minute
limit, then commits. A backfill bigger than that takes several runs.

## The weekly reconcile (`extract --reconcile`)

No update listing shows a deleted or transferred item, so once a week
every item is listed (one request per 100 items, by keyset), and:

1. any item whose `updated_at` differs from the stored one is synced (a
   missed update);
2. any stored item that's no longer listed is synced, which records it as
   gone if it is;
3. the run fails unless every number from 1 to the highest is stored or
   gone.

## Known gaps

- An event skipped by a deletion during a multi-page events read stays
  missing (accepted on 2026-11-15).
- A change that doesn't move an item's `updated_at` (other than events) is
  only fetched when the item next changes, or by the weekly reconcile if
  the listing's `updated_at` differs. None was seen in whatwg/dom's data.
- Untested against the real API (written in a session that couldn't
  reach it): that redirects for transferred issues are 301s with the
  `Location` of the new issue, and that per-item and listed objects have
  the same fields (only `GET /issues/{n}` is stored now, so it no longer
  matters for items).
