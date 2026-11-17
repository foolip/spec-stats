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
    pulls/{n}/commits.json     (optional)
    pulls/{n}/files.json       (optional)
    state.json                 where each part is up to, and numbers that are gone

Git keeps every earlier version, so nothing here keeps history itself.

Items (issues and PRs) are fetched one number at a time, everything for a
number together (sync_item). Which ones: those updated since a start date
(`updated_since` in config/fetch.json), found by listing the repo's items
in order of updated_at. The first listing is the backfill; after it, each
run lists the items updated since the last run (one request if nothing
changed) and syncs those whose updated_at differs from the stored one.
Moving the start date back later lists just the stretch before the old
one (extend_items). Stored items last updated before it are removed
(set_start).

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

PR_RESOURCES = {
    # resource -> (API path, file under pulls/{n}/, paged)
    "pull": ("/repos/{repo}/pulls/{n}", None, False),
    "reviews": ("/repos/{repo}/pulls/{n}/reviews", "reviews", True),
    "commits": ("/repos/{repo}/pulls/{n}/commits", "commits", True),
    "files": ("/repos/{repo}/pulls/{n}/files", "files", True),
}


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


def load_pr_resources():
    names = _config().get("pr_resources", ["pull", "reviews"])
    unknown = set(names) - set(PR_RESOURCES)
    if unknown:
        raise ValueError(f"unknown pr_resources in config/fetch.json: {sorted(unknown)}")
    return names


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

def sync_item(client, store, number, resources, obj=None):
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
            for res in resources:
                path, _, paged = PR_RESOURCES[res]
                url = path.format(repo=repo, n=number)
                if paged:
                    pr[res] = list(_all_pages(client, url))
                    continue
                try:
                    pr[res] = client.rest(url).data
                except Unprocessable as e:  # only /pulls/{n} is unpaged
                    pr[res], refused[res] = None, e.message
            pull = pr.get("pull")
            pr["review_comments"] = (list(_all_pages(client, f"/repos/{repo}/pulls/{number}/comments"))
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
    for res, data in pr.items():
        what = "comments" if res == "review_comments" else PR_RESOURCES[res][1]
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


def _sync_changed(client, store, rows, resources):
    """Sync each listed item whose updated_at differs from the stored one
    (or that isn't stored), storing the row as the item. Returns how many
    were synced."""
    idx, synced = store.index(), 0
    for row in rows:
        if idx.get(row["number"], {}).get("updated_at") != row["updated_at"]:
            sync_item(client, store, row["number"], resources, obj=row)
            synced += 1
    return synced


def _list_and_sync(client, store, resources, since, part, until=None, log=print):
    """List the items updated since `since` (and before `until`), syncing
    the changed ones, and save `part["cursor"]`, the listing's mark
    (the last row's updated_at), after every page: the resume point. A run stopped mid-page lists
    that page again, and skips the items it already synced. Returns how
    many were synced."""
    total = [0]

    def on_page(rows, mark):
        synced = _sync_changed(client, store, rows, resources)
        total[0] += synced
        if mark:
            part["cursor"] = max(mark, part.get("cursor", ""))
        store.save_state()
        if synced:
            log(f"{store.repo} items: synced {synced} of {len(rows)} listed, up to {part['cursor']} "
                f"({client.requests} requests so far)")

    list_ascending(client, f"/repos/{store.repo}/issues", dict(ITEMS, per_page=PER_PAGE, since=since),
                   on_page, until=until)
    return total[0]


def update_items(client, store, resources, log=print):
    """Items updated since the cursor (minus OVERLAP, but not before
    `from`): one request if nothing changed. The first time, there's no
    cursor and this is the backfill: every item updated since `from`."""
    s = store.section("items")
    first = "cursor" not in s
    if first:
        s.setdefault("started", now())
    since = max(s["from"], _minus_overlap(s["cursor"])) if not first else s["from"]
    synced = _list_and_sync(client, store, resources, since, s, log=log)
    s.setdefault("cursor", s["from"])  # nothing updated since `from`
    if "started" in s:
        # The first listing is done. Anything that changed since it
        # started is in the next listing, and any event since then in the
        # first read of the events listing.
        store.section("events").setdefault("cursor", s.pop("started"))
    store.save_state()
    log(f"{store.repo} items: synced {synced} changed (updated since {s['from']})")
    return synced


def extend_items(client, store, resources, since, log=print):
    """When `updated_since` is moved back before `from`: the items updated
    in between, listed by keyset from `since` and stopping at `from`, with
    their own resume point (`items.extend`). Items updated since then are
    the updates' business. Once done, `from` is `since`."""
    s = store.section("items")
    ext = s.get("extend")
    if not ext or ext["from"] != since:
        ext = s["extend"] = {"from": since}
    start = max(since, _minus_overlap(ext["cursor"])) if "cursor" in ext else since
    synced = _list_and_sync(client, store, resources, start, ext, until=s["from"], log=log)
    del s["extend"]
    s["from"] = since
    store.save_state()
    log(f"{store.repo} items: synced {synced} updated since {since}, before the earlier start")


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
    """Apply `updated_since`: stored items last updated before it are
    removed (git keeps them), and so are their 422 records. Moved forward,
    `from` follows it (and a listing back to an earlier date is dropped);
    moved back, extend_items lists the stretch before `from`."""
    s = store.section("items")
    s.setdefault("from", since)
    if since > s["from"]:
        s["from"] = since
        s.pop("extend", None)
    old = sorted(n for n, i in store.index().items() if i["updated_at"] < since)
    for n in old:
        store.remove_item(n)
        store.set_refused(n, None)
    if old:
        store.save_state()
        log(f"{store.repo} items: removed {len(old)} last updated before {since}")


def reconcile(client, store, resources, log=print):
    """Weekly: a second, independent listing of the items. Every item, in
    order of creation, by offset pages (created_at doesn't change, so
    nothing moves around; an item deleted mid-listing can shift one row
    past a page boundary), keeping those updated since `from` on the
    client. Then sync any listed item whose updated_at differs from the
    stored one or that isn't stored (an update listing missed it), and any
    stored item updated since `from` that isn't listed (deleted or
    transferred). (While a listing back to an earlier date is under way,
    its items aren't checked yet.)"""
    s = store.section("items")
    path = f"/repos/{store.repo}/issues"
    params = {"state": "all", "sort": "created", "direction": "asc", "per_page": PER_PAGE}
    listed, total, page = {}, 0, 1
    resp = client.rest(path, params)
    while True:
        total += len(resp.data)
        listed.update((r["number"], r) for r in resp.data if r["updated_at"] >= s["from"])
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
    missed = [n for n in sorted(listed) if n not in idx]
    changed = _sync_changed(client, store, [listed[n] for n in sorted(listed)], resources)
    unlisted = sorted(n for n, i in idx.items() if n not in listed and i["updated_at"] >= s["from"])
    for n in unlisted:
        sync_item(client, store, n, resources)
    store.save_state()
    log(f"{store.repo} reconcile: {total} items listed by creation time, {len(listed)} updated since "
        f"{s['from']}; synced {changed} changed or missing ({len(missed)} weren't stored"
        f"{': ' + _list(missed[:20]) if missed else ''}) and {len(unlisted)} unlisted; "
        f"{len(store.index())} stored, {len(store.gone())} gone")


# --- events ------------------------------------------------------------------

def _without_issue(event):
    """The repo-wide listing embeds a copy of the issue in each event; the
    per-item listing doesn't."""
    return {k: v for k, v in event.items() if k != "issue"}


def _store_events(store, events):
    """Listed events under their issue's number, merged by id, for stored
    items only. The rest are dropped: an item updated before `from` (its
    events come with it if it's updated again), one not fetched yet (they
    will), and deleted and transferred ones (the listing keeps their
    events)."""
    idx = store.index()
    groups = defaultdict(list)
    for obj in events:
        n = obj["issue"]["number"]
        if n in idx:
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

def retry_refused(client, store, resources, log=print):
    """Fetch again every item GitHub refused part of (HTTP 422) on an earlier
    run: such refusals can pass (whatwg/dom #548's did, a run later). The
    record goes once GitHub answers."""
    numbers = sorted(store.refused())
    for n in numbers:
        sync_item(client, store, n, resources)
    if numbers:
        store.save_state()
        still = sorted(store.refused())
        log(f"{store.repo} refused: retried {_list(numbers)}; still refused: {_list(still) or 'none'}")


def _list(numbers):
    return ", ".join(f"#{n}" for n in numbers)


def sync_repo(client, store, reconcile_=False, log=print):
    """Everything for one repo. If the client's deadline stops it midway,
    what's fetched so far is saved and the next run continues."""
    resources = load_pr_resources()
    fixed = store.state.setdefault("pr_resources", resources)
    if fixed != resources:
        raise CheckFailed(f"{store.repo}: config/fetch.json pr_resources is {resources}, but stored PRs "
                          f"have {fixed}; fetching a changed set for every PR isn't implemented")
    since = load_updated_since()
    try:
        migrate_state(store, since)
        set_start(store, since, log=log)
        retry_refused(client, store, resources, log=log)
        update_items(client, store, resources, log=log)
        if since < store.section("items")["from"]:
            extend_items(client, store, resources, since, log=log)
        if reconcile_:
            reconcile(client, store, resources, log=log)
        # After items: the events cursor is set when the first listing finishes.
        sync_events(client, store, log=log)
    finally:
        store.save_state()
