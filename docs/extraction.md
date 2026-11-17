# Extraction: what is fetched and how updates work

Code: `specstats/extract.py` (fetching and storing), `specstats/github.py`
(the serial client). Everything goes in `data/github/`, committed to
this repo, losslessly, as the API returned it, so any analysis can be
run offline, and rerun with new definitions at any time.

The design goal (2026-11-15) is the simplest approach that's complete as
it goes: fetch one issue or PR number at a time, and check assumptions
about GitHub's data by failing loudly rather than working around them.
Since 2026-11-17, "complete" means every item *updated since a start
date* (`updated_since` in `config/fetch.json`, 2024-01-01), not every
item ever: the backfill by number was too slow for its value.

## Where it's stored

One pretty-printed JSON file (2-space indent, GitHub's field order, UTF-8,
trailing newline) per object or per item's list of objects, at a path
that mirrors the API path it comes from:

```
data/github/
  whatwg/html/
    issues/1234/index.json      GET /repos/whatwg/html/issues/1234 (issues and PRs)
    issues/1234/comments.json   GET …/issues/1234/comments
    issues/1234/events.json     GET …/issues/1234/events, plus newer ones from …/issues/events
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
`/issues/{n}/events` returns.

Query the files with `jq` or any JSON tool, e.g.
`jq -r '.[].user.login' data/github/whatwg/html/issues/*/comments.json | sort | uniq -c | sort -n`.

**History is git's.** A changed object rewrites its file; a comment deleted
on GitHub is gone from its list when the item is next fetched; a deleted
or transferred item has all its files removed. Every earlier version is
in `git log`.

whatwg/dom was first fetched on 2026-11-14 by an earlier design
(repo-wide listings of comments, review comments and events, merged by
id). It's being refetched by the current one (2026-11-16): its old
`state.json` was removed, so the backfill starts from #1 and replaces
each number's files as it reaches them; git shows what differs.

## One item: `sync_item(n)`

Everything for one number is fetched together and replaces what's stored:

| Request | When |
|---|---|
| `GET /issues/{n}` | only if the item wasn't listed: its row from the items listing is stored instead (below) |
| `GET /issues/{n}/comments` | if the issue's `comments` count isn't 0 |
| `GET /issues/{n}/events` | always (the issue has no count of them) |
| `GET /pulls/{n}` | PRs, if `pull` is in `config/fetch.json` (default); see below for HTTP 422 |
| `GET /pulls/{n}/reviews` | PRs, if `reviews` is in `config/fetch.json` (default) |
| `GET /pulls/{n}/commits`, `/files` | PRs, if turned on in `config/fetch.json` (off) |
| `GET /pulls/{n}/comments` | PRs, unless `pull` says `review_comments` is 0 |

So a listed issue costs one or two requests and a PR three to five, plus
one per extra page of a long list (one more each when fetched by number:
retrying a 422, or the reconcile's unlisted items).

**The listing's row is the item.** A listed item's row from
`GET /issues?…` is stored as `issues/{n}/index.json`, not fetched again
with `GET /issues/{n}`: `listing-check` (2026-11-17) found them identical
for all 100 whatwg/dom items it compared (the 50 most and 50 least
recently updated, 44 issues and 56 PRs), field for field. An item deleted
or transferred after it was listed is still caught: its other requests
answer 404, 410 or a redirect, and it's recorded as gone. One updated
after it was listed is stored as listed, and is listed again with its new
`updated_at`. `index.json` is written last: its
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

## Items: updated since a start date

Everything is driven by one listing,
`GET /issues?state=all&sort=updated&direction=asc&since=S`, and each
listed item whose `updated_at` differs from the stored one (or that isn't
stored) is synced. `state.json` keeps two dates under `items`:

- `from`: every item updated at or after it is stored, once the first
  listing is done. It starts as `updated_since`.
- `cursor`: the newest `updated_at` seen, saved after every page.

**Backfill.** The first listing, from `S` = `from`. It's an update with
no cursor yet: a run can stop anywhere and the next continues from the
cursor. When it's done, the events listing starts from when it started
(`items.started`, then removed), so whatever changed during it is
fetched again.

**Updates.** Each later run lists from `S` = the cursor minus a day of
overlap (but not before `from`), so anything a run missed (identical
timestamps, a briefly stale API) is listed again.

- `S` only moves when something changed, so an unchanged repo is one
  request, returning an empty page.
- Pages are fetched by *keyset*: each next page is page 1 again, with
  `since` a second before the newest timestamp seen. Following page 2,
  3, … links instead would skip a row whenever an item already read is
  updated mid-listing. A run stopped mid-page lists the page again and
  skips the items it already synced.
- An item last updated before `from` isn't fetched; once it's updated
  (a comment, a label, a transfer into the repo), it's listed and fetched
  whole, history included. So the data has every item active since
  `from`, with all of its activity, also from before `from`.
- Deleted and transferred-out numbers are never listed, so they aren't
  fetched or recorded as gone, unless they were stored (the reconcile).

**Moving the start date.** Moving `updated_since` back, before `from`,
lists just the items updated in between: from the new date by keyset,
stopping at the first row updated at or after `from` (those are the
updates' business). It has its own resume point (`items.extend`: its
`from` and `cursor`), runs after each run's update until done, and then
`from` becomes the new date. Items updated while it runs move past `from`
and are picked up by the next update. Moving `updated_since` forward
does nothing: nothing new to fetch, and nothing stored is dropped.

**Before 2026-11-17** items were backfilled by number, 1 to the highest
(`items.highest` and `items.next`). The first run of the new code
converts that state: a finished backfill (whatwg/fullscreen,
whatwg/dom) stored every item, so `from` becomes its earliest
`updated_at`; an unfinished one (whatwg/html, at #3,753 of 13,270)
starts the listing from `updated_since`, keeps what it stored, and skips
those items it has unchanged. Items stored that were last updated before
`from` stay, and are kept up to date like any other.

This relies on every change to an item's comments, reviews or inline
comments also moving the item's `updated_at`. In whatwg/dom's data that
held for every comment (including 2,146 edited ones), review and inline
comment. It doesn't hold for events, hence the listing below.

## Events: per item, then the repo-wide listing

- **Backfill:** each item's events come with it (`/issues/{n}/events`
  in `sync_item`), so every stored item is complete, events included.
- **Updates:** once the first items listing is done, each run reads the
  repo-wide `GET /issues/events` (newest first), back to a day before
  the newest event seen (usually one page); the first time, back to a
  day before the first listing started. New events are merged into each
  stored item's `events.json` by id. A changed item is refetched whole,
  events included.
- Events of items that aren't stored are dropped: items last updated
  before `from` (an event that moves `updated_at` gets the item listed
  and fetched whole, events included), items not fetched yet, and
  deleted and transferred ones, whose events the listing keeps
  (whatwg/dom had 81 such numbers).

The listing catches events that don't move the item's `updated_at`, so
the item isn't refetched for them. In whatwg/dom that's 1,965 of 14,960
events: mostly `referenced`, `subscribed` and `mentioned`, and
`head_ref_deleted`.

**What the per-item lists leave out:** compared with the repo-wide
listing (whatwg/dom, 2026-11-14 against 2026-11-16), 973 events across 265
items: 893 `referenced` (737 from commits that no longer exist or with no
commit, 145 from forks, 11 from whatwg/dom's own commits), 73
`subscribed`, `mentioned` and `unsubscribed`, and 7 others, including
#831's `closed` (its `closed_at` and `closed_by` are in the issue). The
per-item list seems to drop references GitHub can't resolve any more.
Little of value for maintenance stats, so the backfill doesn't merge in
the repo-wide listing; it's read only for updates, as above.

**Why not the listing for the backfill:** GitHub ends it after 300 pages
(30,000 events) with a full page and no next link, no error.
whatwg/dom's listing reached its first issue, from 2012, in 150 pages;
whatwg/html's ended at 2024-12-06 (seen on 2026-11-15). Between runs, the listing only
needs to reach back a day before the last run.

**Why not the timeline** (`/issues/{n}/timeline`, checked on 2026-11-15
with `timeline-check` on 40 whatwg/dom items): it would replace the
comments request, but not the others.

| | stored | in the timeline |
|---|---|---|
| issue comments | 1,116 | all, identical (`commented`, plus `event` and `actor`) |
| reviews | 386 | 92: not the 294 that only reply in an existing thread; `state`, `user` and `body` differ from `/pulls/{n}/reviews` |
| inline review comments | 576 | 43: only those not part of a review (`line-commented`); a `reviewed` entry has no comments |
| events | 1,801 | 1,613: 188 missing (`referenced` 123 of 360, `subscribed` 33, `mentioned` 30, `closed` 1, `head_ref_force_pushed` 1), with no rule found |

Only the timeline has `cross-referenced` (297 in the sample, with a copy of
the referring issue, often from outside `whatwg/`) and `committed` (git
authorship) entries, neither with an id. Its only parameters are paging
and `exclude` (event types to leave out); nothing adds a review's
comments.

## When a run fails (`CheckFailed`)

The extractor stores what GitHub returns, consistent or not. A run
stores what it fetched and then exits with an error only when fetching
itself can't be done right:

- The repo-wide `/issues/events` doesn't reach back to the last run's
  events: HTTP 422, or a full page (100 events) with no next link, which
  is how GitHub cut off whatwg/html's listing at page 300.
- `config/fetch.json` changed its per-PR resources.
- Any other HTTP 422, except the one below.

**HTTP 422** (`Unprocessable`) isn't a rate limit (those are 403 and
429, and stop the run instead): GitHub won't process that request, and
uses it for unrelated reasons. The request tells which.
`GET /pulls/{n}` answers it for a PR with too many changed files
(whatwg/dom #548, 2026-11-16: "The request could not be processed because
too many files changed"); the rest of the number is stored as usual,
without `pulls/{n}/index.json` (so inline comments are fetched, with no
count to say there are none), and GitHub's message is recorded in
`state.json` under `refused`. Every run starts by fetching refused items
again, changed or not, and the record goes once GitHub answers: #548's
422 passed a run later (its PR has one changed file). Lost for such a PR: what only the pull object has, such
as size and `merged_by` (the `merged` event names who merged it).

## Consistency checks (`check`)

`python3 -m specstats check` reads the stored files (no requests) and
reports, per repo:

- numbers both stored and recorded as gone;
- closed items with no `closed` event, merged PRs with no `merged` event;
- PRs with no `pulls/{n}/index.json` and no 422 recorded for them;
- events stored under a number with no `issues/{n}/index.json`.

Which items *should* be stored, those updated since `from`, can't be told
offline; the weekly reconcile compares them with GitHub's listing. (Until
2026-11-17 it also reported numbers from 1 to the highest that were
neither stored nor gone.)

It also lists what GitHub refused with HTTP 422 (`refused` in
`state.json`), as notes, not findings. It exits with an error if it finds
anything. These are for finding bugs
in the whole process (fetching, storing, committing); a finding can also
be GitHub's own inconsistency, such as whatwg/fullscreen #220, a closed
PR for which GitHub returns no events at all. The "Check data" workflow
(`check.yml`), separate from the fetch, runs it on `main`; it's triggered
manually for now.

## A run (`extract`)

Per repo: items refused with HTTP 422 earlier, the items listing (the
backfill or an update), then the listing back to a moved start date if
there is one, then with `--reconcile` the reconcile, then (once the first
listing is done) the events listing.

A caught-up run of an unchanged repo is two requests, and changes no
files, so there's nothing to commit.

No ETags or conditional requests are used: GitHub's ETags are per token
(`Vary: Authorization`), and Actions' built-in token is new every run,
so a saved ETag never matched (2026-11-15). With a stable token they
would save at most those two requests per run.

## Stopping: deadlines and rate limits

A run stops cleanly, between requests, in two cases: `--max-minutes N`
(no request starts after N minutes), and whenever it would otherwise wait
for rate-limit quota: the hourly budget is down to its reserve (500, or a
tenth of a smaller budget), or GitHub answers with a 429, a secondary
rate limit or an exhausted primary limit. It never idles until a reset.
A stopped run exits normally. The items listing (backfill or update)
continues from the cursor saved per page, and the listing back to a moved
start date from its own. An events read stopped midway saves nothing and
re-reads from the newest next time.

The smallest unit of work is a page of the listing and one PR: five to
seven requests, more for very long lists. Once the first listing is
done, every run also spends at least one request on the events listing.

Each run logs the hourly limit GitHub reports for its token. The
workflow commits after every run. With a 5,000-an-hour token (the
built-in one has had that here) a backfill run stops at the reserve after about 4,500 requests (some 20
minutes), so a backfill takes one run per hour of budget; the 300-minute
deadline, inside the job's 350-minute limit, is a backstop.

## The weekly reconcile (`extract --reconcile`)

No update listing shows a deleted or transferred item, so once a week
every item updated since `from` is listed (one request per 100 items, by
keyset), and:

1. any item whose `updated_at` differs from the stored one is synced (a
   missed update, or one never stored);
2. any stored item updated since `from` that's no longer listed is
   synced, which records it as gone if it is.

Stored items last updated before `from` aren't checked: their deletion
goes unnoticed.

## Known gaps

- Items last updated before `from` aren't fetched (by design since
  2026-11-17), and nothing records that their numbers exist. Numbers
  deleted or transferred out are only recorded as gone if they were
  stored.
- An event skipped by a deletion during a multi-page events read stays
  missing (accepted on 2026-11-15).
- A change that doesn't move an item's `updated_at` (other than events) is
  only fetched when the item next changes, or by the weekly reconcile if
  the listing's `updated_at` differs. None was seen in whatwg/dom's data.
- Untested against the real API (written in a session that couldn't
  reach it): that redirects for transferred issues are 301s with the
  `Location` of the new issue. (That per-item and listed objects have
  the same fields was checked by `listing-check` on 2026-11-17, above.)
