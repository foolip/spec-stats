"""Fetch everything that happens on a repo's issues and PRs from the GitHub REST API.

Every object is stored as plain JSON text, exactly the fields GitHub
returned, in data/private/raw.sqlite, so it can be queried directly
(`SELECT json_pretty(json) FROM items ...`) and everything downstream can
be rebuilt offline. When a stored object changes, its previous version is
kept in `history`.

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
unchanged stream costs one free 304. See docs/extraction.md.
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from . import paths
from .github import NotFound, PaginationLimit

OVERLAP = timedelta(days=1)
PER_PAGE = 100

# table -> (key columns after repo, extra columns, timestamp column, history mode)
# history mode: "ts" keeps the old version when the timestamp changes,
# "json" when the JSON changes (objects without updated_at), None never.
TABLES = {
    "items": (["number"], ["is_pr"], "updated_at", "ts"),
    "issue_comments": (["id"], ["number"], "updated_at", "ts"),
    "review_comments": (["id"], ["number", "review_id"], "updated_at", "ts"),
    "events": (["id"], ["number"], "created_at", None),
    "pulls": (["number"], [], "updated_at", "ts"),
    "pr_reviews": (["id"], ["number"], "submitted_at", "json"),
    "pr_commits": (["number", "sha"], [], None, "json"),
    "pr_files": (["number", "filename"], [], None, "json"),
}

PR_RESOURCES = {
    # resource -> (path, table, paged)
    "pull": ("/repos/{repo}/pulls/{n}", "pulls", False),
    "reviews": ("/repos/{repo}/pulls/{n}/reviews", "pr_reviews", True),
    "commits": ("/repos/{repo}/pulls/{n}/commits", "pr_commits", True),
    "files": ("/repos/{repo}/pulls/{n}/files", "pr_files", True),
}


COLUMN_TYPES = {"number": "INTEGER", "id": "INTEGER", "is_pr": "INTEGER", "review_id": "INTEGER",
                "sha": "TEXT", "filename": "TEXT"}


def _schema():
    out = []
    for table, (keys, extra, ts, _) in TABLES.items():
        cols = (["repo TEXT NOT NULL"] + [f"{k} {COLUMN_TYPES[k]} NOT NULL" for k in keys]
                + [f"{k} {COLUMN_TYPES[k]}" for k in extra])
        if ts:
            cols.append(ts + " TEXT")
        cols += ["node_id TEXT", "json TEXT NOT NULL", f"PRIMARY KEY (repo, {', '.join(keys)})"]
        out.append(f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(cols)});")
        if "number" in extra:
            out.append(f"CREATE INDEX IF NOT EXISTS {table}_number ON {table}(repo, number);")
    out.append("""
CREATE TABLE IF NOT EXISTS users (
  login TEXT PRIMARY KEY,
  updated_at TEXT,
  fetched_at TEXT NOT NULL,
  node_id TEXT,
  json TEXT NOT NULL              -- REST user object, or {"login", "missing": true}
);
CREATE TABLE IF NOT EXISTS history (
  -- previous versions of objects that changed, newest last
  tbl TEXT NOT NULL,
  repo TEXT,
  key TEXT NOT NULL,              -- JSON array of the key columns
  replaced_at TEXT NOT NULL,      -- when we saw the new version
  removed INTEGER NOT NULL DEFAULT 0,  -- 1: the object was gone on refetch
  json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS history_key ON history(tbl, repo, key);
CREATE TABLE IF NOT EXISTS pr_fetched (
  -- which per-PR resources are current for which version of the PR
  repo TEXT NOT NULL,
  number INTEGER NOT NULL,
  resource TEXT NOT NULL,
  item_updated_at TEXT NOT NULL,
  PRIMARY KEY (repo, number, resource)
);
CREATE TABLE IF NOT EXISTS item_events (
  -- items whose events were fetched one by one (fallback when the
  -- repo-wide events listing can't be paged back far enough)
  repo TEXT NOT NULL,
  number INTEGER NOT NULL,
  item_updated_at TEXT NOT NULL,
  PRIMARY KEY (repo, number)
);
CREATE TABLE IF NOT EXISTS gone (
  -- issue numbers that don't exist here: deleted, or transferred elsewhere
  repo TEXT NOT NULL,
  number INTEGER NOT NULL,
  reason TEXT NOT NULL,           -- 'deleted' | 'transferred'
  checked_at TEXT NOT NULL,
  PRIMARY KEY (repo, number)
);
CREATE TABLE IF NOT EXISTS cursors (
  repo TEXT NOT NULL,
  stream TEXT NOT NULL,
  cursor TEXT,                    -- newest updated_at (created_at for events) stored
  etag TEXT,                      -- ETag of the first page requested with since_used
  since_used TEXT,
  floor TEXT,                     -- events only: oldest created_at reached, '' = all
  PRIMARY KEY (repo, stream)
);
""")
    return "\n".join(out)


def connect(path=None):
    db = sqlite3.connect(path or paths.raw_db())
    db.executescript(_schema())
    return db


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(ts):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _fmt(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _tail_number(url):
    return int(url.rstrip("/").rsplit("/", 1)[1])


def _dump(obj):
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def load_pr_resources():
    p = paths.CONFIG / "fetch.json"
    names = json.loads(p.read_text())["pr_resources"] if p.exists() else ["pull", "reviews"]
    unknown = set(names) - set(PR_RESOURCES)
    if unknown:
        raise ValueError(f"unknown pr_resources in config/fetch.json: {sorted(unknown)}")
    return names


# --- storing ---------------------------------------------------------------

def _columns(table, obj, number=None):
    """Column values for one object of `table` (everything but repo and json)."""
    if table == "items":
        return {"number": obj["number"], "is_pr": int("pull_request" in obj), "updated_at": obj["updated_at"]}
    if table == "issue_comments":
        return {"id": obj["id"], "number": _tail_number(obj["issue_url"]), "updated_at": obj["updated_at"]}
    if table == "review_comments":
        return {"id": obj["id"], "number": _tail_number(obj["pull_request_url"]),
                "review_id": obj.get("pull_request_review_id"), "updated_at": obj["updated_at"]}
    if table == "events":
        return {"id": obj["id"], "number": number if number is not None else obj["issue"]["number"],
                "created_at": obj["created_at"]}
    if table == "pulls":
        return {"number": obj["number"], "updated_at": obj["updated_at"]}
    if table == "pr_reviews":
        return {"id": obj["id"], "number": number, "submitted_at": obj.get("submitted_at")}
    if table == "pr_commits":
        return {"number": number, "sha": obj["sha"]}
    if table == "pr_files":
        return {"number": number, "filename": obj["filename"]}
    raise ValueError(table)


def store(db, repo, table, obj, number=None):
    """Upsert one REST object, keeping the old version in `history` if it
    changed. Returns the object's timestamp (None if it has none)."""
    keys, _, ts_col, mode = TABLES[table]
    cols = _columns(table, obj, number)
    new_json = _dump(obj)
    where = " AND ".join(f"{k} = ?" for k in keys)
    key_vals = [cols[k] for k in keys]
    old = db.execute(f"SELECT {ts_col or 'NULL'}, json FROM {table} WHERE repo = ? AND {where}",
                     [repo, *key_vals]).fetchone()
    if old and mode and old[1] != new_json and (mode == "json" or old[0] != cols.get(ts_col)):
        _keep(db, table, repo, key_vals, old[1])
    cols.update(repo=repo, node_id=obj.get("node_id"), json=new_json)
    names = list(cols)
    db.execute(f"INSERT OR REPLACE INTO {table} ({', '.join(names)}) VALUES ({', '.join('?' * len(names))})",
               [cols[n] for n in names])
    return cols.get(ts_col) if ts_col else None


def _keep(db, table, repo, key_vals, old_json, removed=False):
    db.execute("INSERT INTO history (tbl, repo, key, replaced_at, removed, json) VALUES (?,?,?,?,?,?)",
               (table, repo, json.dumps(key_vals), now(), int(removed), old_json))


def replace_set(db, repo, table, number, objs):
    """Store all of one item's objects in `table` (e.g. a PR's reviews), and
    move ones that are no longer there to history."""
    keys = TABLES[table][0]
    old = db.execute(f"SELECT {', '.join(keys)}, json FROM {table} WHERE repo = ? AND number = ?",
                     (repo, number)).fetchall()
    seen = set()
    for obj in objs:
        cols = _columns(table, obj, number)
        seen.add(tuple(cols[k] for k in keys))
        store(db, repo, table, obj, number)
    for row in old:
        key_vals = row[:-1]
        if tuple(key_vals) not in seen:
            _keep(db, table, repo, list(key_vals), row[-1], removed=True)
            where = " AND ".join(f"{k} = ?" for k in keys)
            db.execute(f"DELETE FROM {table} WHERE repo = ? AND {where}", [repo, *key_vals])


def _cursor(db, repo, stream):
    row = db.execute("SELECT cursor, etag, since_used, floor FROM cursors WHERE repo=? AND stream=?",
                     (repo, stream)).fetchone()
    return row or (None, None, None, None)


def _save_cursor(db, repo, stream, cursor, etag, since_used, floor=None):
    db.execute("INSERT OR REPLACE INTO cursors VALUES (?,?,?,?,?,?)",
               (repo, stream, cursor, etag, since_used, floor))
    db.commit()


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


def list_ascending(client, path, params, on_page, first=None, log=print):
    """Page through an ascending `since` listing, starting from `first` if
    it's already been requested. If GitHub refuses to page that deep (HTTP
    422), restart with `since` at the newest timestamp reached; `since` is
    inclusive, so the boundary rows come again and are harmlessly re-stored.
    `on_page(rows)` stores a page and returns the newest timestamp."""
    resp = first or client.rest(path, params)
    while True:
        newest = on_page(resp.data)
        if not resp.next:
            return
        try:
            resp = client.rest(resp.next)
        except PaginationLimit:
            if newest is None or newest == params.get("since"):
                raise
            log(f"{path}: pagination limit, restarting from {newest}")
            params = dict(params, since=newest)
            resp = client.rest(path, params)


def sync_ascending(client, db, repo, stream, log=print):
    """Fetch everything in `stream` updated since the cursor (minus OVERLAP)."""
    path, base = ASCENDING[stream]
    path = path.format(repo=repo)
    cursor, etag, since_used, _ = _cursor(db, repo, stream)
    since = _fmt(_parse(cursor) - OVERLAP) if cursor else None
    params = dict(base, per_page=PER_PAGE)
    if since:
        params["since"] = since
    first = client.rest(path, params, etag=etag if since_used == since else None)
    if first.status == 304:
        log(f"{repo} {stream}: unchanged")
        return 0
    state = {"newest": cursor, "stored": 0}

    def on_page(rows):
        for obj in rows:
            ts = store(db, repo, stream, obj)
            state["newest"] = max(state["newest"] or ts, ts)
            state["stored"] += 1
        db.commit()
        _save_cursor(db, repo, stream, state["newest"], None, None)  # resume point
        return state["newest"]

    list_ascending(client, path, params, on_page, first=first, log=log)
    _save_cursor(db, repo, stream, state["newest"], first.etag, since)
    log(f"{repo} {stream}: stored {state['stored']}")
    return state["stored"]


# --- events ----------------------------------------------------------------

def sync_events(client, db, repo, log=print):
    """Repo-wide events, newest first, until OVERLAP before the cursor.

    If GitHub won't page back to the start of history (first run), the
    oldest event reached is recorded as `floor`, and fetch_item_events()
    covers older items one at a time.
    """
    cursor, etag, _, floor = _cursor(db, repo, "events")
    stop = _fmt(_parse(cursor) - OVERLAP) if cursor else None
    resp = client.rest(f"/repos/{repo}/issues/events", {"per_page": PER_PAGE}, etag=etag if cursor else None)
    if resp.status == 304:
        log(f"{repo} events: unchanged")
        return 0
    first_etag = resp.etag
    newest, oldest, stored, reached_end = cursor, None, 0, False
    while True:
        done = False
        for obj in resp.data:
            ts = obj["created_at"]
            if stop and ts < stop:
                done = True
                break
            if obj.get("issue"):
                store(db, repo, "events", obj)
                stored += 1
            newest = max(newest or ts, ts)
            oldest = min(oldest or ts, ts)
        db.commit()
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
    if cursor is None:
        floor = "" if reached_end else oldest
    _save_cursor(db, repo, "events", newest, first_etag, None, floor)
    log(f"{repo} events: stored {stored}")
    return stored


def fetch_item_events(client, db, repo, log=print):
    """Per-item events for items older than the events floor, if there is one."""
    _, _, _, floor = _cursor(db, repo, "events")
    if not floor:
        return 0
    todo = db.execute(
        "SELECT i.number, i.updated_at FROM items i LEFT JOIN item_events e "
        "ON e.repo = i.repo AND e.number = i.number "
        "WHERE i.repo = ? AND json_extract(i.json, '$.created_at') < ? "
        "AND (e.item_updated_at IS NULL OR e.item_updated_at != i.updated_at)",
        (repo, floor)).fetchall()
    for number, updated in todo:
        for obj in _all_pages(client, f"/repos/{repo}/issues/{number}/events"):
            store(db, repo, "events", obj, number)
        db.execute("INSERT OR REPLACE INTO item_events VALUES (?,?,?)", (repo, number, updated))
        db.commit()
    if todo:
        log(f"{repo} events: fetched per-item events for {len(todo)} older items")
    return len(todo)


# --- per-PR resources --------------------------------------------------------

def stale_prs(db, repo, resource):
    return db.execute(
        "SELECT i.number, i.updated_at FROM items i LEFT JOIN pr_fetched f "
        "ON f.repo = i.repo AND f.number = i.number AND f.resource = ? "
        "WHERE i.repo = ? AND i.is_pr = 1 "
        "AND (f.item_updated_at IS NULL OR f.item_updated_at != i.updated_at) ORDER BY i.number",
        (resource, repo)).fetchall()


def sync_pr_resources(client, db, repo, resources=None, log=print):
    """Fetch each configured per-PR resource for every PR that changed."""
    total = 0
    for resource in resources or load_pr_resources():
        path, table, paged = PR_RESOURCES[resource]
        todo = stale_prs(db, repo, resource)
        for number, updated in todo:
            url = path.format(repo=repo, n=number)
            try:
                if paged:
                    replace_set(db, repo, table, number, _all_pages(client, url))
                else:
                    store(db, repo, table, client.rest(url).data)
            except NotFound:
                pass  # deleted since it was listed; reconcile records it
            db.execute("INSERT OR REPLACE INTO pr_fetched VALUES (?,?,?,?)", (repo, number, resource, updated))
            db.commit()
        if todo:
            log(f"{repo} {resource}: fetched for {len(todo)} PRs")
        total += len(todo)
    return total


# --- consistency checks ------------------------------------------------------

def comment_mismatches(db, repo):
    """Items whose stored comments don't match the counts GitHub reports:
    conversation comments (`comments` on the issue) and inline review
    comments (`review_comments` on the PR, if `pull` is fetched)."""
    issue = db.execute(
        "SELECT i.number FROM items i WHERE i.repo = ? AND "
        "json_extract(i.json, '$.comments') != "
        "(SELECT COUNT(*) FROM issue_comments c WHERE c.repo = i.repo AND c.number = i.number)",
        (repo,)).fetchall()
    review = db.execute(
        "SELECT p.number FROM pulls p JOIN items i ON i.repo = p.repo AND i.number = p.number "
        "WHERE p.repo = ? AND p.updated_at = i.updated_at AND "
        "json_extract(p.json, '$.review_comments') != "
        "(SELECT COUNT(*) FROM review_comments c WHERE c.repo = p.repo AND c.number = p.number)",
        (repo,)).fetchall()
    return [n for (n,) in issue], [n for (n,) in review]


def check_counts(client, db, repo, log=print):
    """Refetch the comments of items whose stored counts are off. This also
    moves comments that were deleted on GitHub to history."""
    issue_bad, review_bad = comment_mismatches(db, repo)
    for number in issue_bad:
        replace_set(db, repo, "issue_comments", number, _all_pages(client, f"/repos/{repo}/issues/{number}/comments"))
    for number in review_bad:
        replace_set(db, repo, "review_comments", number, _all_pages(client, f"/repos/{repo}/pulls/{number}/comments"))
    db.commit()
    if issue_bad or review_bad:
        log(f"{repo}: refetched comments for {len(issue_bad)} items and review comments for {len(review_bad)} PRs")
    return issue_bad, review_bad


def reconcile(client, db, repo, log=print):
    """Weekly check that every issue and PR is stored.

    Re-lists every item (storing any that changed), then accounts for every
    number from 1 to the highest: each one is stored, or recorded in `gone`
    as deleted or transferred after checking it on GitHub. Items stored here
    but missing from the listing are checked the same way.
    """
    remote = {}

    def on_page(rows):
        for obj in rows:
            remote[obj["number"]] = obj["updated_at"]
            store(db, repo, "items", obj)
        db.commit()
        return rows[-1]["updated_at"] if rows else None

    list_ascending(client, f"/repos/{repo}/issues",
                   {"state": "all", "sort": "updated", "direction": "asc", "per_page": PER_PAGE}, on_page, log=log)
    stored = {n for (n,) in db.execute("SELECT number FROM items WHERE repo = ?", (repo,))}
    gone = {n for (n,) in db.execute("SELECT number FROM gone WHERE repo = ?", (repo,))}
    highest = max(set(remote) | stored, default=0)
    to_check = sorted((set(range(1, highest + 1)) - set(remote) - gone))
    found, marked = [], {}
    for number in to_check:
        try:
            obj = client.rest(f"/repos/{repo}/issues/{number}").data
        except NotFound:
            marked[number] = "deleted"
            continue
        if obj["repository_url"].lower().endswith("/repos/" + repo.lower()):
            store(db, repo, "items", obj)
            found.append(number)
        else:
            marked[number] = "transferred"
    for number, reason in marked.items():
        db.execute("INSERT OR REPLACE INTO gone VALUES (?,?,?,?)", (repo, number, reason, now()))
        row = db.execute("SELECT json FROM items WHERE repo = ? AND number = ?", (repo, number)).fetchone()
        if row:
            _keep(db, "items", repo, [number], row[0], removed=True)
            db.execute("DELETE FROM items WHERE repo = ? AND number = ?", (repo, number))
    db.commit()
    stored_now = db.execute("SELECT COUNT(*) FROM items WHERE repo = ?", (repo,)).fetchone()[0]
    gone_now = db.execute("SELECT COUNT(*) FROM gone WHERE repo = ?", (repo,)).fetchone()[0]
    report = {"repo": repo, "highest": highest, "stored": stored_now, "gone": gone_now,
              "found": found, "newly_gone": sorted(marked)}
    log(f"{repo} reconcile: numbers 1..{highest}: {stored_now} stored, {gone_now} gone; "
        f"found {len(found)} missing, marked {len(marked)} gone")
    return report


# --- whole repo ----------------------------------------------------------------

def sync_repo(client, db, repo, log=print):
    for stream in ASCENDING:
        sync_ascending(client, db, repo, stream, log=log)
    sync_events(client, db, repo, log=log)
    fetch_item_events(client, db, repo, log=log)
    sync_pr_resources(client, db, repo, log=log)
    check_counts(client, db, repo, log=log)


# --- users -----------------------------------------------------------------------

def seen_logins(db):
    """Logins of every human account that appears anywhere in the raw data."""
    logins = set()
    for table, paths_ in (("items", ("$.user", "$.closed_by")), ("issue_comments", ("$.user",)),
                          ("review_comments", ("$.user",)), ("events", ("$.actor",)),
                          ("pulls", ("$.merged_by",)), ("pr_reviews", ("$.user",))):
        for p in paths_:
            for (login,) in db.execute(
                    f"SELECT DISTINCT json_extract(json, '{p}.login') FROM {table} "
                    f"WHERE json_extract(json, '{p}.type') = 'User'"):
                if login:
                    logins.add(login)
    return logins


def users_to_fetch(db):
    have = {r[0] for r in db.execute("SELECT login FROM users")}
    return sorted(seen_logins(db) - have)


def extract_users(client, db, logins, log=print):
    """Fetch the public profiles (name, company, …) of `logins`."""
    for i, login in enumerate(logins, 1):
        try:
            obj = client.rest(f"/users/{login}").data
        except NotFound:
            obj = {"login": login, "missing": True}
        old = db.execute("SELECT updated_at, json FROM users WHERE login = ?", (login,)).fetchone()
        if old and old[0] != obj.get("updated_at"):
            _keep(db, "users", None, [login], old[1])
        db.execute("INSERT OR REPLACE INTO users VALUES (?,?,?,?,?)",
                   (login, obj.get("updated_at"), now(), obj.get("node_id"), _dump(obj)))
        db.commit()
        if i % 100 == 0 or i == len(logins):
            log(f"users: {i}/{len(logins)}")
