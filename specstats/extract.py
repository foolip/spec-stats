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
number together (sync_item). The backfill walks the numbers from 1 to the
highest; after it, each run lists the items updated since the last run
(one request, a free 304 if nothing changed and the token is the same as
the last run's: GitHub's ETags are per token) and syncs those whose updated_at differs
from the stored one.

Events are part of an item (GET /issues/{n}/events, fetched with it).
After the backfill, each run also reads the repo-wide /issues/events
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
from .github import GitHubError, Gone, PaginationLimit

OVERLAP = timedelta(days=1)
PER_PAGE = 100
STATE_EVERY = 50  # save state.json after this many items
# Log backfill progress about every 10-20 requests: an item takes about 3.7
# (whatwg/dom: the issue, its events, comments if any, and for a PR the
# pull, reviews and review comments if any).
PROGRESS_EVERY = 5  # items

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


def load_pr_resources():
    p = paths.CONFIG / "fetch.json"
    names = json.loads(p.read_text())["pr_resources"] if p.exists() else ["pull", "reviews"]
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

    def save_state(self):
        s = dict(self.state)
        if "gone" in s:
            s["gone"] = {k: s["gone"][k] for k in sorted(s["gone"], key=int)}
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

def sync_item(client, store, number, resources):
    """Fetch everything for one issue or PR number and replace what's stored.

    index.json is written last, so its updated_at says the item is synced:
    a run stopped midway refetches the item. A number that's deleted,
    transferred elsewhere (a redirect, not followed) or never existed is
    recorded as gone, and anything stored for it is removed.
    """
    repo = store.repo
    try:
        obj = client.rest(f"/repos/{repo}/issues/{number}").data
        comments = (list(_all_pages(client, f"/repos/{repo}/issues/{number}/comments"))
                    if obj["comments"] else None)
        events = [_without_issue(e) for e in _all_pages(client, f"/repos/{repo}/issues/{number}/events")]
        pr = {}
        if "pull_request" in obj:
            for res in resources:
                path, _, paged = PR_RESOURCES[res]
                url = path.format(repo=repo, n=number)
                pr[res] = list(_all_pages(client, url)) if paged else client.rest(url).data
            pull = pr.get("pull")
            pr["review_comments"] = (list(_all_pages(client, f"/repos/{repo}/pulls/{number}/comments"))
                                     if pull is None or pull["review_comments"] else None)
    except Gone:
        store.remove_item(number)
        store.set_gone(number)
        return None
    store.unset_gone(number)
    store.put("issues", number, "comments", comments)
    store.put("issues", number, "events", events)
    for res, data in pr.items():
        what = "comments" if res == "review_comments" else PR_RESOURCES[res][1]
        store.put("pulls", number, what, data)
    store.put("issues", number, None, obj)
    return obj


def _sync_through(client, store, number, resources):
    """Make every number up to `number` stored or gone: sync the numbers
    between the highest known and `number`, which is new."""
    s = store.section("items")
    while s["highest"] < number:
        sync_item(client, store, s["highest"] + 1, resources)
        s["highest"] += 1


# --- items -------------------------------------------------------------------

ITEMS = {"state": "all", "sort": "updated", "direction": "asc"}


def find_highest(client, repo):
    """The highest issue or PR number. The newest-created item usually has
    it, but an issue transferred in later keeps its creation date and gets
    a higher number; a transfer moves updated_at, so it's among the items
    updated since the newest was created."""
    newest = client.rest(f"/repos/{repo}/issues",
                         {"state": "all", "sort": "created", "direction": "desc", "per_page": 1}).data
    if not newest:
        return 0
    highest = newest[0]["number"]
    for row in _all_pages(client, f"/repos/{repo}/issues",
                          {"state": "all", "sort": "updated", "direction": "desc",
                           "since": newest[0]["created_at"]}):
        highest = max(highest, row["number"])
    return highest


def backfill_items(client, store, resources, log=print):
    """Every number from 1 to the highest, one at a time. Resumes from `next`."""
    s = store.section("items")
    if "highest" not in s:
        s["started"] = now()
        s["highest"] = find_highest(client, store.repo)
        s["next"] = 1
        store.save_state()
    done = 0
    while s["next"] <= s["highest"]:
        sync_item(client, store, s["next"], resources)
        s["next"] += 1
        done += 1
        if done % STATE_EVERY == 0:
            store.save_state()
        if done % PROGRESS_EVERY == 0:
            log(f"{store.repo} items: backfilled up to {s['next'] - 1} of {s['highest']} "
                f"({done} this run, {client.requests} requests so far)")
    # Anything created, transferred in or updated since the backfill
    # started is in the first update's listing, and any event since then
    # in the first read of the events listing.
    s["cursor"] = s.pop("started")
    store.section("events").setdefault("cursor", s["cursor"])
    del s["next"]
    store.save_state()
    log(f"{store.repo} items: backfilled numbers 1..{s['highest']} ({done} this run)")


def list_ascending(client, path, params, on_page, first=None):
    """Page through an ascending listing by *keyset*: each next page is page 1
    again with `since` just before the newest timestamp seen so far.

    Following page 2, 3, ... links would skip a row whenever a row already
    read is updated mid-listing (it moves to the end, and the row after the
    page boundary slides back unread). Only if a whole page shares one
    second does this follow the offset link for that stretch.

    `first` is the already-requested first page, if any. `on_page(rows)`
    handles a page and returns its newest updated_at.
    """
    per_page = int(params.get("per_page", PER_PAGE))
    resp = first or client.rest(path, params)
    since = params.get("since")
    while True:
        newest = on_page(resp.data)
        if len(resp.data) < per_page or not resp.next:
            return
        next_since = _fmt(_parse(newest) - timedelta(seconds=1))
        if since is None or next_since > since:
            since = next_since
            resp = client.rest(path, dict(params, since=since))
        else:
            try:
                resp = client.rest(resp.next)
            except PaginationLimit:
                raise GitHubError(f"{path}: more rows at {newest} than GitHub will page through")


def _sync_changed(client, store, rows, resources):
    """Sync each listed item whose updated_at differs from the stored one
    (or that isn't stored). Returns how many were synced."""
    idx, synced = store.index(), 0
    for row in rows:
        n = row["number"]
        _sync_through(client, store, n - 1, resources)
        if idx.get(n, {}).get("updated_at") != row["updated_at"]:
            sync_item(client, store, n, resources)
            synced += 1
        s = store.section("items")
        s["highest"] = max(s["highest"], n)
    return synced


def update_items(client, store, resources, log=print):
    """Items updated since the cursor (minus OVERLAP). The first page carries
    the last ETag for the same `since`, so an unchanged repo is one request,
    a free 304 if the token is the same as the last run's."""
    s = store.section("items")
    since = _minus_overlap(s["cursor"])
    path = f"/repos/{store.repo}/issues"
    params = dict(ITEMS, per_page=PER_PAGE, since=since)
    first = client.rest(path, params, etag=s.get("etag") if s.get("etag_since") == since else None)
    if first.status == 304:
        log(f"{store.repo} items: unchanged")
        return 0
    total = [0]

    def on_page(rows):
        total[0] += _sync_changed(client, store, rows, resources)
        if rows:
            s["cursor"] = max(s["cursor"], max(r["updated_at"] for r in rows))
        store.save_state()  # resume point
        return max((r["updated_at"] for r in rows), default=None)

    list_ascending(client, path, params, on_page, first=first)
    s["etag"], s["etag_since"] = first.etag, since
    store.save_state()
    log(f"{store.repo} items: synced {total[0]} changed")
    return total[0]


def reconcile(client, store, resources, log=print):
    """Weekly: list every item, and sync any whose updated_at differs (missed
    updates) or that's stored but no longer listed (deleted or transferred).
    `check` then finds any number up to the highest that's neither stored
    nor gone."""
    listed = {}

    def on_page(rows):
        for r in rows:
            listed[r["number"]] = r["updated_at"]
        return rows[-1]["updated_at"] if rows else None

    list_ascending(client, f"/repos/{store.repo}/issues", dict(ITEMS, per_page=PER_PAGE), on_page)
    idx = store.index()
    rows = [{"number": n, "updated_at": u} for n, u in sorted(listed.items())]
    changed = _sync_changed(client, store, rows, resources)
    unlisted = sorted(set(idx) - set(listed))
    for n in unlisted:
        sync_item(client, store, n, resources)
    store.save_state()
    highest = store.section("items")["highest"]
    log(f"{store.repo} reconcile: synced {changed} changed and {len(unlisted)} unlisted; "
        f"numbers 1..{highest}: {len(store.index())} stored, {len(store.gone())} gone")


# --- events ------------------------------------------------------------------

def _without_issue(event):
    """The repo-wide listing embeds a copy of the issue in each event; the
    per-item listing doesn't."""
    return {k: v for k, v in event.items() if k != "issue"}


def _store_events(store, events):
    """Listed events under their issue's number, merged by id. Events of
    numbers recorded as gone are dropped: the listing keeps deleted issues'
    events. Events stored before their number is found to be gone are
    removed with it."""
    gone = store.gone()
    groups = defaultdict(list)
    for obj in events:
        n = obj["issue"]["number"]
        if n not in gone:
            groups[n].append(_without_issue(obj))
    for n, objs in groups.items():
        store.merge("issues", n, "events", objs)


def sync_events(client, store, log=print):
    """After the items backfill: the repo-wide events listing, newest
    first, back to OVERLAP before the newest event seen (at first, before
    the backfill started). Merged into each item's events."""
    s = store.section("events")
    if "cursor" not in s:
        return  # set when the items backfill finishes
    path = f"/repos/{store.repo}/issues/events"
    resp = client.rest(path, {"per_page": PER_PAGE}, etag=s.get("etag"))
    if resp.status == 304:
        log(f"{store.repo} events: unchanged")
        return
    first_etag, stop, newest, stored = resp.etag, _minus_overlap(s["cursor"]), s["cursor"], 0
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
        except PaginationLimit:
            raise CheckFailed(f"{store.repo}: GitHub won't page /issues/events back to {stop}")
    s["cursor"], s["etag"] = newest, first_etag
    store.save_state()
    log(f"{store.repo} events: stored {stored}")


# --- whole repo ----------------------------------------------------------------

def sync_repo(client, store, reconcile_=False, log=print):
    """Everything for one repo. If the client's deadline stops it midway,
    what's fetched so far is saved and the next run continues."""
    resources = load_pr_resources()
    fixed = store.state.setdefault("pr_resources", resources)
    if fixed != resources:
        raise CheckFailed(f"{store.repo}: config/fetch.json pr_resources is {resources}, but stored PRs "
                          f"have {fixed}; fetching a changed set for every PR isn't implemented")
    try:
        items = store.section("items")
        if "cursor" not in items:
            backfill_items(client, store, resources, log=log)
        else:
            update_items(client, store, resources, log=log)
            if reconcile_:
                reconcile(client, store, resources, log=log)
        # After items: the events cursor is set when the backfill finishes.
        sync_events(client, store, log=log)
    finally:
        store.save_state()
