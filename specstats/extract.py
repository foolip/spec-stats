"""Fetch everything that happens on a repo's issues and PRs from the GitHub REST API.

Every object is stored exactly as GitHub returned it, as pretty-printed
JSON files committed to this repo, laid out like the API paths
(docs/extraction.md):

  data/github/{owner}/{repo}/
    issues/{n}/index.json      the issue (or the issue view of a PR)
    issues/{n}/comments.json   conversation comments, by id
    issues/{n}/events.json     timeline events, by id
    pulls/{n}/index.json       the PR view: merged_by, size, ...
    pulls/{n}/reviews.json     reviews
    pulls/{n}/comments.json    inline review comments, by id
    pulls/{n}/commits.json     (optional)
    pulls/{n}/files.json       (optional)
    state.json                 cursors, ETags, what was fetched when, gone numbers

Git keeps every earlier version, so nothing here keeps history itself.

Per repo there are four *streams*, each a listing of the whole repo:

  items            /issues            every issue and PR (sort=updated, asc, since)
  issue_comments   /issues/comments   every conversation comment (asc, since)
  review_comments  /pulls/comments    every inline review comment (asc, since)
  events           /issues/events     every timeline event (newest first, no since)

and, for each PR whose `updated_at` changed, the per-PR resources listed in
config/fetch.json (REST has no repo-wide listing of these):

  pull     /pulls/{n}           merged_by, size, review comment count
  reviews  /pulls/{n}/reviews   states and bodies
  commits  /pulls/{n}/commits   (optional)
  files    /pulls/{n}/files     (optional)

Each ascending stream re-reads OVERLAP before its cursor, so anything an
earlier run missed is picked up; the cursor advances page by page, so an
interrupted run resumes; and the first page carries the last ETag, so an
unchanged stream costs one free 304.
"""

import json
import shutil
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import paths
from .github import DeadlineReached, GitHubError, NotFound, PaginationLimit

OVERLAP = timedelta(days=1)
PER_PAGE = 100
STATE_EVERY = 50  # save state.json after this many per-item fetches

PR_RESOURCES = {
    # resource -> (API path, file under pulls/, paged)
    "pull": ("/repos/{repo}/pulls/{n}", None, False),
    "reviews": ("/repos/{repo}/pulls/{n}/reviews", "reviews", True),
    "commits": ("/repos/{repo}/pulls/{n}/commits", "commits", True),
    "files": ("/repos/{repo}/pulls/{n}/files", "files", True),
}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(ts):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _fmt(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _tail_number(url):
    return int(url.rstrip("/").rsplit("/", 1)[1])


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


def _by_number(d):
    return {k: d[k] for k in sorted(d, key=int)}


class RepoStore:
    """One repo's files, data/github/{owner}/{repo}/."""

    def __init__(self, repo, root=None):
        self.repo = repo
        self.dir = Path(root or paths.github_dir()) / repo
        self.state = read_json(self.dir / "state.json", {})
        self._index = None

    # state.json
    def cursor(self, stream):
        return self.state.get("cursors", {}).get(stream, {})

    def set_cursor(self, stream, **fields):
        self.state.setdefault("cursors", {})[stream] = {k: v for k, v in fields.items() if v is not None}
        self.save_state()

    def fetched(self, resource, number):
        return self.state.get("fetched", {}).get(resource, {}).get(str(number))

    def set_fetched(self, resource, number, updated_at):
        self.state.setdefault("fetched", {}).setdefault(resource, {})[str(number)] = updated_at

    def gone(self):
        return {int(n): v for n, v in self.state.get("gone", {}).items()}

    def set_gone(self, number, reason):
        self.state.setdefault("gone", {})[str(number)] = {"reason": reason, "checked_at": now()}

    def save_state(self):
        s = dict(self.state)
        if "fetched" in s:
            s["fetched"] = {r: _by_number(m) for r, m in sorted(s["fetched"].items())}
        if "gone" in s:
            s["gone"] = _by_number(s["gone"])
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

    def put_issue(self, obj):
        self.put("issues", obj["number"], None, obj)

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
        self._index[obj["number"]] = {"updated_at": obj["updated_at"], "created_at": obj["created_at"],
                                      "is_pr": "pull_request" in obj, "comments": obj.get("comments", 0)}

    def index(self):
        """number -> {updated_at, created_at, is_pr, comments}, from issues/*/index.json."""
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
    """owner/name of every repo with files, e.g. ["whatwg/dom"]."""
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


# --- the ascending streams -------------------------------------------------

ASCENDING = {
    "items": ("/repos/{repo}/issues", {"state": "all", "sort": "updated", "direction": "asc"}),
    "issue_comments": ("/repos/{repo}/issues/comments", {"sort": "updated", "direction": "asc"}),
    "review_comments": ("/repos/{repo}/pulls/comments", {"sort": "updated", "direction": "asc"}),
}


def _store_page(store, stream, rows):
    """Store one page of an ascending stream."""
    if stream == "items":
        for obj in rows:
            store.put_issue(obj)
        return
    groups = defaultdict(list)
    for obj in rows:
        if stream == "issue_comments":
            groups[("issues", _tail_number(obj["issue_url"]))].append(obj)
        else:
            groups[("pulls", _tail_number(obj["pull_request_url"]))].append(obj)
    for (kind, number), objs in groups.items():
        store.merge(kind, number, "comments", objs)


def list_ascending(client, path, params, on_page, first=None, log=print):
    """Page through an ascending listing by *keyset*: each next page is page 1
    again with `since` just before the newest timestamp seen so far, rather
    than page 2, 3, ... of the original request.

    Offset pages shift when a row we've already read is updated mid-listing
    (it moves to the end, and the row after our page boundary slides back
    into it, unread). Keyset pages can't skip rows, and they never page deep
    enough to hit GitHub's pagination limit. Rows in the overlapping second
    are re-read and harmlessly re-stored. Only if a whole page shares one
    timestamp does this follow the offset link for that stretch.

    `first` is the already-requested first page, if any. `on_page(rows)`
    stores a page and returns the newest timestamp.
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
            # A full page within one second: step through it by offset.
            try:
                resp = client.rest(resp.next)
            except PaginationLimit:
                raise GitHubError(f"{path}: more rows at {newest} than GitHub will page through")


def sync_ascending(client, store, stream, log=print):
    """Fetch everything in `stream` updated since the cursor (minus OVERLAP)."""
    repo = store.repo
    path, base = ASCENDING[stream]
    path = path.format(repo=repo)
    c = store.cursor(stream)
    cursor = c.get("cursor")
    since = _fmt(_parse(cursor) - OVERLAP) if cursor else None
    params = dict(base, per_page=PER_PAGE)
    if since:
        params["since"] = since
    first = client.rest(path, params, etag=c.get("etag") if c.get("since") == since else None)
    if first.status == 304:
        log(f"{repo} {stream}: unchanged")
        return 0
    state = {"newest": cursor, "stored": 0}

    def on_page(rows):
        _store_page(store, stream, rows)
        for obj in rows:
            state["newest"] = max(state["newest"] or obj["updated_at"], obj["updated_at"])
        state["stored"] += len(rows)
        store.set_cursor(stream, cursor=state["newest"])  # resume point
        return state["newest"]

    list_ascending(client, path, params, on_page, first=first, log=log)
    store.set_cursor(stream, cursor=state["newest"], etag=first.etag, since=since)
    log(f"{repo} {stream}: stored {state['stored']}")
    return state["stored"]


# --- events ----------------------------------------------------------------

def _store_events(store, events):
    """Events from the repo-wide listing, under their issue's number. The
    embedded `issue` (a copy of the issue at fetch time) is left out, so
    they're stored as /issues/{n}/events returns them."""
    groups = defaultdict(list)
    for obj in events:
        groups[obj["issue"]["number"]].append({k: v for k, v in obj.items() if k != "issue"})
    for number, objs in groups.items():
        store.merge("issues", number, "events", objs)


def sync_events(client, store, log=print):
    """Repo-wide events, newest first, until OVERLAP before the cursor.

    If GitHub won't page back to the start of history (first run), the
    oldest event reached is recorded as `floor`, and fetch_item_events()
    covers older items one at a time. A first run stopped by the deadline
    does the same, as a newest-first listing can't be resumed midway.
    """
    repo = store.repo
    c = store.cursor("events")
    cursor, floor = c.get("cursor"), c.get("floor")
    stop = _fmt(_parse(cursor) - OVERLAP) if cursor else None
    resp = client.rest(f"/repos/{repo}/issues/events", {"per_page": PER_PAGE},
                       etag=c.get("etag") if cursor else None)
    if resp.status == 304:
        log(f"{repo} events: unchanged")
        return 0
    first_etag = resp.etag
    newest, oldest, stored, reached_end = cursor, None, 0, False
    while True:
        done = False
        page = []
        for obj in resp.data:
            ts = obj["created_at"]
            if stop and ts < stop:
                done = True
                break
            if obj.get("issue"):
                page.append(obj)
            newest = max(newest or ts, ts)
            oldest = min(oldest or ts, ts)
        _store_events(store, page)
        stored += len(page)
        if done:
            break
        if not resp.next:
            reached_end = True
            break
        try:
            resp = client.rest(resp.next)
        except PaginationLimit:
            log(f"{repo} events: pagination limit at {oldest}; older items fall back to per-item events")
            break
        except DeadlineReached:
            if cursor is None and oldest:
                store.set_cursor("events", cursor=newest, etag=first_etag, floor=oldest)
                log(f"{repo} events: stopped at {oldest}; older items fall back to per-item events")
            raise
    if cursor is None:
        floor = "" if reached_end else oldest
    store.set_cursor("events", cursor=newest, etag=first_etag, floor=floor)
    log(f"{repo} events: stored {stored}")
    return stored


def fetch_item_events(client, store, log=print):
    """Per-item events for items older than the events floor, if there is one."""
    floor = store.cursor("events").get("floor")
    if not floor:
        return 0
    todo = [(n, i["updated_at"]) for n, i in sorted(store.index().items())
            if i["created_at"] < floor and store.fetched("events", n) != i["updated_at"]]
    for k, (number, updated) in enumerate(todo, 1):
        store.merge("issues", number, "events", _all_pages(client, f"/repos/{store.repo}/issues/{number}/events"))
        store.set_fetched("events", number, updated)
        if k % STATE_EVERY == 0:
            store.save_state()
    store.save_state()
    if todo:
        log(f"{store.repo} events: fetched per-item events for {len(todo)} older items")
    return len(todo)


# --- per-PR resources --------------------------------------------------------

def stale_prs(store, resource):
    return [(n, i["updated_at"]) for n, i in sorted(store.index().items())
            if i["is_pr"] and store.fetched(resource, n) != i["updated_at"]]


def sync_pr_resources(client, store, resources=None, log=print):
    """Fetch each configured per-PR resource for every PR that changed."""
    total = 0
    for resource in resources or load_pr_resources():
        path, what, paged = PR_RESOURCES[resource]
        todo = stale_prs(store, resource)
        for k, (number, updated) in enumerate(todo, 1):
            url = path.format(repo=store.repo, n=number)
            try:
                data = list(_all_pages(client, url)) if paged else client.rest(url).data
                store.put("pulls", number, what, data)
            except NotFound:
                pass  # deleted since it was listed; reconcile records it
            store.set_fetched(resource, number, updated)
            if k % STATE_EVERY == 0:
                store.save_state()
        store.save_state()
        if todo:
            log(f"{store.repo} {resource}: fetched for {len(todo)} PRs")
        total += len(todo)
    return total


# --- consistency checks ------------------------------------------------------

def comment_mismatches(store):
    """Items whose stored comments don't match the counts GitHub reports:
    conversation comments (`comments` on the issue) and inline review
    comments (`review_comments` on the PR, if `pull` is fetched)."""
    issue, review = [], []
    for number, info in sorted(store.index().items()):
        if info["comments"] != len(store.get("issues", number, "comments", [])):
            issue.append(number)
        if info["is_pr"]:
            pull = store.get("pulls", number)
            if (pull and pull["updated_at"] == info["updated_at"]
                    and pull.get("review_comments") != len(store.get("pulls", number, "comments", []))):
                review.append(number)
    return issue, review


def check_counts(client, store, log=print):
    """Refetch the comments of items whose stored counts are off. Comments
    deleted on GitHub are dropped (git keeps them)."""
    issue_bad, review_bad = comment_mismatches(store)
    for kind, bad in (("issues", issue_bad), ("pulls", review_bad)):
        for number in bad:
            objs = list(_all_pages(client, f"/repos/{store.repo}/{kind}/{number}/comments"))
            store.put(kind, number, "comments", sorted(objs, key=lambda o: o["id"]))
    if issue_bad or review_bad:
        log(f"{store.repo}: refetched comments for {len(issue_bad)} items and review comments for {len(review_bad)} PRs")
    return issue_bad, review_bad


def reconcile(client, store, log=print):
    """Weekly check that every issue and PR is stored.

    Re-lists every item (storing any that changed), then accounts for every
    number from 1 to the highest: each one is stored, or recorded as gone
    (deleted or transferred) in state.json after checking it on GitHub.
    Items stored here but missing from the listing are checked the same way.
    """
    repo = store.repo
    remote = set()

    def on_page(rows):
        for obj in rows:
            remote.add(obj["number"])
            store.put_issue(obj)
        return rows[-1]["updated_at"] if rows else None

    list_ascending(client, f"/repos/{repo}/issues",
                   {"state": "all", "sort": "updated", "direction": "asc", "per_page": PER_PAGE}, on_page, log=log)
    stored = set(store.index())
    gone = set(store.gone())
    highest = max(remote | stored, default=0)
    to_check = sorted(set(range(1, highest + 1)) - remote - gone)
    found, marked = [], {}
    for number in to_check:
        try:
            obj = client.rest(f"/repos/{repo}/issues/{number}").data
        except NotFound:
            marked[number] = "deleted"
            continue
        if obj["repository_url"].lower().endswith("/repos/" + repo.lower()):
            store.put_issue(obj)
            found.append(number)
        else:
            marked[number] = "transferred"
    for number, reason in marked.items():
        store.set_gone(number, reason)
        store.remove_item(number)
    store.save_state()
    report = {"repo": repo, "highest": highest, "stored": len(store.index()), "gone": len(store.gone()),
              "found": found, "newly_gone": sorted(marked)}
    log(f"{repo} reconcile: numbers 1..{highest}: {report['stored']} stored, {report['gone']} gone; "
        f"found {len(found)} missing, marked {len(marked)} gone")
    return report


# --- whole repo ----------------------------------------------------------------

def sync_repo(client, store, log=print):
    """Everything for one repo. If the client's deadline stops it midway,
    what's fetched so far is saved and the next run continues."""
    try:
        for stream in ASCENDING:
            sync_ascending(client, store, stream, log=log)
        sync_events(client, store, log=log)
        fetch_item_events(client, store, log=log)
        sync_pr_resources(client, store, log=log)
        check_counts(client, store, log=log)
    finally:
        store.save_state()
