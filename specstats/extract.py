"""Fetch everything that happens on a repo's issues and PRs from the GitHub REST API.

Every object is stored exactly as GitHub returned it, as pretty-printed
JSON files committed to this repo, laid out like the API paths
(docs/extraction.md):

  data/github/{owner}/{repo}/
    issues/{n}/index.json      GET /issues/{n} (the issue, or the issue view of a PR)
    issues/{n}/comments.json   GET /issues/{n}/comments
    issues/{n}/events.json     GET /issues/{n}/events, plus newer ones from /issues/events
    pulls/{n}/index.json       GET /pulls/{n}
    pulls/{n}/reviews.json     GET /pulls/{n}/reviews
    pulls/{n}/comments.json    GET /pulls/{n}/comments
    state.json                 where each part is up to, and numbers that are gone

Git keeps every earlier version, so nothing here keeps history itself.

Items (issues and PRs) are fetched one number at a time, everything for a
number together (sync_item). Which ones: those updated since a start date
(`updated_since` in config/fetch.json), found by listing the repo's items
in order of updated_at. The first listing is the backfill; after it, each
run lists the items updated since the last run (one request if nothing
changed) and syncs those whose updated_at differs from the stored one.
Moving the start date back later lists just the stretch before the old
one (extend_items). Open items are fetched too, however long ago they
were last updated: they're listed once (list_open_items), and after that
any change moves them into the updates' listing. Every other item, closed
and last updated before the start date, is stored as its listing row alone
(issues/{n}/index.json, no details), from the weekly reconcile, which
lists every item (set_start strips the details of items that fall behind
a start date moved forward).

Events are part of an item (GET /issues/{n}/events, fetched with it).
After the first listing, each run also reads the repo-wide /issues/events
listing, newest first, back to the last run's newest event (one request
if there are none, as above): it has the events that don't move an item's
updated_at, so the item isn't refetched for them. The listing can't be
the backfill: GitHub ends it after 300 pages (whatwg/html: back to
2024-12-06).

The data is stored as GitHub returns it, consistent or not; a run fails
(CheckFailed) only when fetching itself can't be done right: GitHub won't
page the events listing back far enough, or config/fetch.json changed.
Consistency checks on the stored data are separate (check.py).
"""

import json
import shutil
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import paths
from .github import GitHubError, Gone, Unprocessable

OVERLAP = timedelta(days=1)
PER_PAGE = 100

class CheckFailed(Exception):
    """Fetching can't be done right; the run stores what it has and fails."""

    """An assumption about GitHub's data didn't hold. What was fetched is
    stored; the run reports this and exits with an error."""


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(ts):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _fmt(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _minus_overlap(ts):
    return _fmt(_parse(ts) - OVERLAP)


def _config():
    p = paths.CONFIG / "fetch.json"
    return json.loads(p.read_text()) if p.exists() else {}


def load_updated_since():
    """The start date: items updated at or after it are fetched."""
    ts = _config().get("updated_since", "2022-01-01T00:00:00Z")
    _parse(ts)  # the format the listings use
    return ts


# --- files ---------------------------------------------------------------------

def pretty(data):
    """GitHub's field order, 2-space indent, UTF-8, trailing newline."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path, data):
    """Write `data` if it differs from what's there; None or [] removes the file
    (and its directory, if that leaves it empty)."""
    path = Path(path)
    if data is None or data == []:
        if path.exists():
            path.unlink()
            try:
                path.parent.rmdir()
            except OSError:
                pass
        return
    text = pretty(data)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


class RepoGone(Exception):
    """GitHub answers 404 for the repo itself (not public yet, renamed or
    deleted). The run skips it; with nothing stored for it, no files are
    written."""


class RepoStore:
    """One repo's files, data/github/{owner}/{repo}/."""

    def __init__(self, repo, root=None):
        self.repo = repo
        self.dir = Path(root or paths.github_dir()) / repo
        self.state = read_json(self.dir / "state.json", {})
        self._index = None

    # state.json
    def section(self, name):
        return self.state.setdefault(name, {})

    def gone(self):
        return {int(n) for n in self.state.get("gone", {})}

    def set_gone(self, number):
        self.state.setdefault("gone", {})[str(number)] = {"checked_at": now()}

    def unset_gone(self, number):
        self.state.get("gone", {}).pop(str(number), None)

    def refused(self):
        """number -> {resource: GitHub's message}: what GitHub answered with
        HTTP 422 for an item that's otherwise stored."""
        return {int(n): r for n, r in self.state.get("refused", {}).items()}

    def set_refused(self, number, refused):
        if refused:
            self.state.setdefault("refused", {})[str(number)] = dict(refused, checked_at=now())
        else:
            self.state.get("refused", {}).pop(str(number), None)

    def save_state(self):
        s = dict(self.state)
        for key in ("gone", "refused"):
            if key in s:
                s[key] = {k: s[key][k] for k in sorted(s[key], key=int)}
        write_json(self.dir / "state.json", s)

    # objects
    def path(self, kind, number, what=None):
        return self.dir / kind / str(number) / f"{what or 'index'}.json"

    def get(self, kind, number, what=None, default=None):
        return read_json(self.path(kind, number, what), default)

    def put(self, kind, number, what, data):
        write_json(self.path(kind, number, what), data)
        if kind == "issues" and what is None and self._index is not None:
            self._remember(data)

    def merge(self, kind, number, what, objs):
        """Add or replace objects by id in a list file, kept sorted by id."""
        by_id = {o["id"]: o for o in self.get(kind, number, what, [])}
        for o in objs:
            by_id[o["id"]] = o
        self.put(kind, number, what, [by_id[i] for i in sorted(by_id)])

    def full(self, number):
        """Whether a stored item has its details (comments, events, pulls/):
        updated since `from`, or open. The rest are their row alone."""
        return _full(self.index()[number], self.state.get("items", {}).get("from", ""))

    def strip_details(self, number):
        """Remove everything stored for a number but its row; whether there
        was anything."""
        stripped = False
        for what in ("comments", "events"):
            path = self.path("issues", number, what)
            if path.exists():
                path.unlink()
                stripped = True
        pulls = self.dir / "pulls" / str(number)
        if pulls.exists():
            shutil.rmtree(pulls)
            stripped = True
        return stripped

    def remove_item(self, number):
        """Everything stored for a deleted or transferred issue or PR."""
        for kind in ("issues", "pulls"):
            shutil.rmtree(self.dir / kind / str(number), ignore_errors=True)
        if self._index is not None:
            self._index.pop(number, None)

    # a small in-memory index of the issue files
    def _remember(self, obj):
        self._index[obj["number"]] = {
            "updated_at": obj["updated_at"], "created_at": obj["created_at"], "state": obj["state"],
            "is_pr": "pull_request" in obj, "merged": bool((obj.get("pull_request") or {}).get("merged_at"))}

    def index(self):
        """number -> {updated_at, created_at, state, is_pr, merged}, from issues/*/index.json."""
        if self._index is None:
            self._index = {}
            for p in self.dir.glob("issues/*/index.json"):
                if p.parent.name.isdigit():
                    self._remember(read_json(p))
        return self._index

    def lists(self, kind, what):
        """(number, objects) for every issues/{n}/{what}.json or pulls/{n}/{what}.json."""
        for p in sorted(self.dir.glob(f"{kind}/*/{what}.json"), key=lambda p: int(p.parent.name)):
            yield int(p.parent.name), read_json(p)

    def counts(self):
        idx = self.index()
        out = {"issues": sum(not i["is_pr"] for i in idx.values()), "prs": sum(i["is_pr"] for i in idx.values()),
               "row_only": sum(not self.full(n) for n in idx),
               "pulls": len(list(self.dir.glob("pulls/*/index.json")))}
        for name, kind, what in (("comments", "issues", "comments"), ("events", "issues", "events"),
                                 ("reviews", "pulls", "reviews"), ("review_comments", "pulls", "comments")):
            out[name] = sum(len(objs) for _, objs in self.lists(kind, what))
        out["gone"] = len(self.gone())
        return out


def stored_repos(root=None):
    """owner/name of every repo with files, e.g. ["whatwg/html"]."""
    root = Path(root or paths.github_dir())
    if not root.is_dir():
        return []
    return sorted(f"{o.name}/{r.name}" for o in root.iterdir() if o.is_dir()
                  for r in o.iterdir() if r.is_dir())


def _all_pages(client, path, params=None):
    resp = client.rest(path, dict(params or {}, per_page=PER_PAGE))
    while True:
        yield from resp.data
        if not resp.next:
            return
        resp = client.rest(resp.next)


# --- one item ------------------------------------------------------------------

def sync_item(client, store, number, obj=None):
    """Fetch everything for one issue or PR number and replace what's stored.

    `obj` is the item's row from the items listing, if it was listed: the
    same object as GET /issues/{n} returns (`listing-check`, 2026-11-17),
    so that request is saved. Without it, the item is fetched by number.

    index.json is written last, so its updated_at says the item is synced:
    a run stopped midway refetches the item. A number that's deleted,
    transferred elsewhere (a redirect, not followed) or never existed is
    recorded as gone, and anything stored for it is removed: any of its
    requests answers 404, 410 or a redirect then.

    GET /pulls/{n} answers HTTP 422 for a PR with too many changed files
    (whatwg/dom #548). The rest of the number is stored without
    pulls/{n}/index.json, and GitHub's message is recorded in state.json
    under "refused". Any other 422 fails the run.
    """
    repo = store.repo
    try:
        if obj is None:
            obj = client.rest(f"/repos/{repo}/issues/{number}").data
        comments = (list(_all_pages(client, f"/repos/{repo}/issues/{number}/comments"))
                    if obj["comments"] else None)
        events = [_without_issue(e) for e in _all_pages(client, f"/repos/{repo}/issues/{number}/events")]
        pr, refused = {}, {}
        if "pull_request" in obj:
            try:
                pull = client.rest(f"/repos/{repo}/pulls/{number}").data
            except Unprocessable as e:
                pull, refused["pull"] = None, e.message
            pr[None] = pull
            pr["reviews"] = list(_all_pages(client, f"/repos/{repo}/pulls/{number}/reviews"))
            pr["comments"] = (list(_all_pages(client, f"/repos/{repo}/pulls/{number}/comments"))
                              if pull is None or pull["review_comments"] else None)
    except Gone:
        store.remove_item(number)
        store.set_gone(number)
        store.set_refused(number, None)
        return None
    store.unset_gone(number)
    store.set_refused(number, refused)
    store.put("issues", number, "comments", comments)
    store.put("issues", number, "events", events)
    for what, data in pr.items():
        store.put("pulls", number, what, data)
    store.put("issues", number, None, obj)
    return obj


# --- items -------------------------------------------------------------------

ITEMS = {"state": "all", "sort": "updated", "direction": "asc"}


def list_ascending(client, path, params, on_page, until=None):
    """Page through an ascending listing by *keyset*: each next page is page 1
    again with `since` just before the page's *mark*, the updated_at of its
    last row.

    Following page 2, 3, ... links would skip a row whenever a row already
    read is updated mid-listing (it moves to the end, and the row after the
    page boundary slides back unread). Only if the keyset can't move on (a
    whole page sharing one second) does this follow the offset link for
    that stretch.

    The last row, not the newest: GitHub sorts by a timestamp that's
    sometimes older than the updated_at it returns (whatwg/html #127,
    #2973, #1518 and #7617, 2026-11-17, came among rows updated by
    2026-10-02 with updated_at from 2026-10-08 to 2026-10-19), and going on
    from the page's newest skipped the 98 items in between. A skip is
    still possible if such a row ends a page; the reconcile, which lists
    by creation time, catches it.

    `on_page(rows, mark)` handles a page. With `until`, rows updated at or
    after it are left out, and the listing stops once the mark reaches it.
    """
    per_page = int(params.get("per_page", PER_PAGE))
    resp = client.rest(path, params)
    since = params.get("since")
    while True:
        mark = resp.data[-1]["updated_at"] if resp.data else None
        on_page([r for r in resp.data if until is None or r["updated_at"] < until], mark)
        if len(resp.data) < per_page or not resp.next or (until is not None and mark >= until):
            return
        next_since = _fmt(_parse(mark) - timedelta(seconds=1))
        if since is None or next_since > since:
            since = next_since
            resp = client.rest(path, dict(params, since=since))
        else:
            try:
                resp = client.rest(resp.next)
            except Unprocessable as e:
                raise GitHubError(f"{path}: more rows at {mark} than GitHub will page through ({e.message})")


def _sync_changed(client, store, rows, closed_too=False):
    """Sync each listed item whose updated_at differs from the stored one
    (or that isn't stored, or with `closed_too`, that's closed: it may be
    stored as its row alone), storing the row as the item. Returns how
    many were synced."""
    idx, synced = store.index(), 0
    for row in rows:
        if ((closed_too and row["state"] != "open")
                or idx.get(row["number"], {}).get("updated_at") != row["updated_at"]):
            sync_item(client, store, row["number"], obj=row)
            synced += 1
    return synced


def _list_and_sync(client, store, since, part, until=None, params=ITEMS, closed_too=False, log=print):
    """List the items updated since `since` (and before `until`), syncing
    the changed ones, and save `part["cursor"]`, the listing's mark
    (the last row's updated_at), after every page: the resume point. A run stopped mid-page lists
    that page again, and skips the items it already synced. Returns how
    many were synced."""
    total = [0]

    def on_page(rows, mark):
        synced = _sync_changed(client, store, rows, closed_too=closed_too)
        total[0] += synced
        if mark:
            part["cursor"] = max(mark, part.get("cursor", ""))
        store.save_state()
        if synced:
            log(f"{store.repo} items: synced {synced} of {len(rows)} listed, up to {part['cursor']} "
                f"({client.requests} requests so far)")

    params = dict(params, per_page=PER_PAGE)
    if since is not None:
        params["since"] = since
    list_ascending(client, f"/repos/{store.repo}/issues", params, on_page, until=until)
    return total[0]


def update_items(client, store, log=print):
    """Items updated since the cursor (minus OVERLAP, but not before
    `from`): one request if nothing changed. The first time, there's no
    cursor and this is the backfill: every item updated since `from`."""
    s = store.section("items")
    first = "cursor" not in s
    if first:
        s.setdefault("started", now())
    since = max(s["from"], _minus_overlap(s["cursor"])) if not first else s["from"]
    synced = _list_and_sync(client, store, since, s, log=log)
    s.setdefault("cursor", s["from"])  # nothing updated since `from`
    if "started" in s:
        # The first listing is done. Anything that changed since it
        # started is in the next listing, and any event since then in the
        # first read of the events listing.
        store.section("events").setdefault("cursor", s.pop("started"))
    store.save_state()
    log(f"{store.repo} items: synced {synced} changed (updated since {s['from']})")
    return synced


def extend_items(client, store, since, log=print):
    """When `updated_since` is moved back before `from`: the items updated
    in between, listed by keyset from `since` and stopping at `from`, with
    their own resume point (`items.extend`). Items updated since then are
    the updates' business. Once done, `from` is `since`. Every closed item
    listed is synced, unchanged or not: it may be stored as its row alone,
    and now gets its details. (Open ones have them already.) A run stopped
    midway syncs the closed items of the page it stopped in again."""
    s = store.section("items")
    ext = s.get("extend")
    if not ext or ext["from"] != since:
        ext = s["extend"] = {"from": since}
    start = max(since, _minus_overlap(ext["cursor"])) if "cursor" in ext else since
    synced = _list_and_sync(client, store, start, ext, until=s["from"], closed_too=True, log=log)
    del s["extend"]
    s["from"] = since
    store.save_state()
    log(f"{store.repo} items: synced {synced} updated since {since}, before the earlier start")


OPEN_ITEMS = {"state": "open", "sort": "updated", "direction": "asc"}


def list_open_items(client, store, log=print):
    """Once per repo: the open items last updated before `from`, listed by
    keyset from the oldest and stopping at `from` (those after it are the
    updates' business), with their own resume point (`items.open`). After
    that, an open item can't drop out of the data: any change to it, such
    as closing it, moves its updated_at past `from`, so the updates list
    it; and set_start keeps open items, however old. A new `updated_since`
    doesn't need a new listing: moved back, it only adds items; moved
    forward, the open ones between the two dates are stored already."""
    s = store.section("items")
    part = s.setdefault("open", {})
    if part.get("done"):
        return
    since = _minus_overlap(part["cursor"]) if "cursor" in part else None
    synced = _list_and_sync(client, store, since, part, until=s["from"], params=OPEN_ITEMS, log=log)
    s["open"] = {"done": True}
    store.save_state()
    log(f"{store.repo} items: synced {synced} open, last updated before {s['from']}")


def migrate_state(store, since):
    """state.json from the by-number backfill (items.highest, until
    2026-11-17) to the by-updated_at one (items.from = `since`). A
    finished backfill keeps its cursor: it's caught up. An unfinished one
    starts listing from `since`, and skips the items it has unchanged."""
    s = store.section("items")
    if "highest" not in s:
        return
    if "next" in s:
        s.clear()
    else:
        del s["highest"]
    s["from"] = since
    store.save_state()


def set_start(store, since, log=print):
    """Apply `updated_since`: stored closed items last updated before it
    keep only their row: their details are removed (git keeps them), and
    so are their 422 records. Open ones keep everything (list_open_items). Moved forward,
    `from` follows it (and a listing back to an earlier date is dropped);
    moved back, extend_items lists the stretch before `from`."""
    s = store.section("items")
    s.setdefault("from", since)
    if since > s["from"]:
        s["from"] = since
        s.pop("extend", None)
    old = [n for n, i in sorted(store.index().items()) if not _full(i, since)]
    stripped = [n for n in old if store.strip_details(n) | (n in store.refused())]
    for n in stripped:
        store.set_refused(n, None)
    if stripped:
        store.save_state()
        log(f"{store.repo} items: kept only the row of {len(stripped)} closed, last updated before {since}")


def _full(item, since):
    """Whether an item is stored with its details (comments, events, and
    for a PR its pull object, reviews and inline comments): updated since
    `since`, or open. The rest are stored as their row alone."""
    return item["updated_at"] >= since or item["state"] == "open"


def sync_row(client, store, number):
    """GET /issues/{n} for a stored item the reconcile didn't list: recorded
    as gone if it is, synced whole if it should have its details now, and
    otherwise its row stored."""
    try:
        obj = client.rest(f"/repos/{store.repo}/issues/{number}").data
    except Gone:
        store.remove_item(number)
        store.set_gone(number)
        store.set_refused(number, None)
        return
    if _full(obj, store.section("items")["from"]):
        sync_item(client, store, number, obj=obj)
    else:
        store.strip_details(number)
        store.put("issues", number, None, obj)


def reconcile(client, store, log=print):
    """Weekly: a second, independent listing of the items. Every item, in
    order of creation, by offset pages (created_at doesn't change, so
    nothing moves around; an item deleted mid-listing can shift one row
    past a page boundary). Then:

    - sync any listed item updated since `from` or open whose updated_at
      differs from the stored one or that isn't stored (an update listing
      missed it);
    - store the row of every other listed item, if it differs from the
      stored one (these have no details);
    - fetch any stored item that isn't listed (deleted or transferred).

    `items.rows` records when every item was last listed: from then on,
    every number up to the highest listed is stored or gone, or was never
    listed (check). (While a listing back to an earlier date is under way,
    its items get their details from that listing.)"""
    s = store.section("items")
    path = f"/repos/{store.repo}/issues"
    params = {"state": "all", "sort": "created", "direction": "asc", "per_page": PER_PAGE}
    started = now()
    listed, total, page = {}, 0, 1
    resp = client.rest(path, params)
    while True:
        total += len(resp.data)
        listed.update((r["number"], r) for r in resp.data)
        if len(resp.data) < PER_PAGE:
            break
        page += 1
        try:
            # A full page with no next link is either the last page or, as
            # GitHub ends /issues/events after 300 pages, a cut-off: ask
            # for the next page by number to tell.
            resp = client.rest(resp.next) if resp.next else client.rest(path, dict(params, page=page))
        except Unprocessable as e:
            raise CheckFailed(f"{store.repo}: GitHub won't page the reconcile's listing past {total} items "
                              f"({e.message})")
        if not resp.data:
            break
    idx = store.index()
    full = [n for n in sorted(listed) if _full(listed[n], s["from"])]
    missed = [n for n in full if n not in idx]
    changed = _sync_changed(client, store, [listed[n] for n in full])
    rows = 0
    for n in sorted(set(listed) - set(full)):
        if n not in idx or store.get("issues", n) != listed[n]:
            store.strip_details(n)
            store.put("issues", n, None, listed[n])
            rows += 1
    unlisted = sorted(n for n in idx if n not in listed)
    for n in unlisted:
        if store.full(n):
            sync_item(client, store, n)
        else:
            sync_row(client, store, n)
    s["rows"] = started
    store.save_state()
    log(f"{store.repo} reconcile: {total} items listed by creation time, {len(full)} updated since "
        f"{s['from']} or open; synced {changed} changed or missing ({len(missed)} weren't stored"
        f"{': ' + _list(missed[:20]) if missed else ''}), stored {rows} other rows new or changed, "
        f"fetched {len(unlisted)} unlisted; {len(store.index())} stored, {len(store.gone())} gone")


# --- events ------------------------------------------------------------------

def _without_issue(event):
    """The repo-wide listing embeds a copy of the issue in each event; the
    per-item listing doesn't."""
    return {k: v for k, v in event.items() if k != "issue"}


def _store_events(store, events):
    """Listed events under their issue's number, merged by id, for items
    stored with their details only. The rest are dropped: an item stored as
    its row alone (its events come with it if it's updated again), one not
    fetched yet (they will), and deleted and transferred ones (the listing
    keeps their events)."""
    idx = store.index()
    groups = defaultdict(list)
    for obj in events:
        n = obj["issue"]["number"]
        if n in idx and store.full(n):
            groups[n].append(_without_issue(obj))
    for n, objs in groups.items():
        store.merge("issues", n, "events", objs)


def sync_events(client, store, log=print):
    """After the first items listing: the repo-wide events listing, newest
    first, back to OVERLAP before the newest event seen (at first, before
    that listing started). Merged into each stored item's events."""
    s = store.section("events")
    if "cursor" not in s:
        return  # set when the first items listing finishes
    path = f"/repos/{store.repo}/issues/events"
    resp = client.rest(path, {"per_page": PER_PAGE})
    stop, newest, stored = _minus_overlap(s["cursor"]), s["cursor"], 0
    while True:
        rows = [e for e in resp.data if e["created_at"] >= stop]
        _store_events(store, rows)
        stored += len(rows)
        newest = max([newest] + [e["created_at"] for e in rows])
        if len(rows) < len(resp.data):
            break
        if not resp.next:
            if len(resp.data) == PER_PAGE:
                # GitHub ends this listing silently after 300 pages: a full
                # page with no next link.
                raise CheckFailed(f"{store.repo}: /issues/events ended (a full page with no next link) "
                                  f"before reaching {stop}")
            break
        try:
            resp = client.rest(resp.next)
        except Unprocessable as e:
            raise CheckFailed(f"{store.repo}: GitHub won't page /issues/events back to {stop} ({e.message})")
    s["cursor"] = newest
    store.save_state()
    log(f"{store.repo} events: stored {stored}")


# --- whole repo ----------------------------------------------------------------

def retry_refused(client, store, log=print):
    """Fetch again every item GitHub refused part of (HTTP 422) on an earlier
    run: such refusals can pass (whatwg/dom #548's did, a run later). The
    record goes once GitHub answers."""
    numbers = sorted(store.refused())
    for n in numbers:
        sync_item(client, store, n)
    if numbers:
        store.save_state()
        still = sorted(store.refused())
        log(f"{store.repo} refused: retried {_list(numbers)}; still refused: {_list(still) or 'none'}")


def _list(numbers):
    return ", ".join(f"#{n}" for n in numbers)


def sync_repo(client, store, reconcile_=False, log=print):
    """Everything for one repo. If the client's deadline stops it midway,
    what's fetched so far is saved and the next run continues."""
    since = load_updated_since()
    gone = False
    try:
        migrate_state(store, since)
        set_start(store, since, log=log)
        retry_refused(client, store, log=log)
        update_items(client, store, log=log)
        if since < store.section("items")["from"]:
            extend_items(client, store, since, log=log)
        list_open_items(client, store, log=log)
        if reconcile_:
            reconcile(client, store, log=log)
        # After items: the events cursor is set when the first listing finishes.
        sync_events(client, store, log=log)
    except Gone as e:
        # An item's 404 is handled where it's fetched, so this is the repo's.
        gone = True
        raise RepoGone(f"{store.repo}: {e}") from e
    finally:
        if not gone or store.dir.exists():
            store.save_state()
