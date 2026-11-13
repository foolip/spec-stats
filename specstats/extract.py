"""Fetch everything that happens on a repo's issues and PRs from the GitHub API.

Raw responses are kept losslessly in data/private/raw.sqlite, so all
downstream steps can be rebuilt offline. Per repo there are four
*streams*, each a REST listing of the whole repo:

  items            /issues            every issue and PR (sort=updated, asc, since)
  issue_comments   /issues/comments   every conversation comment (asc, since)
  review_comments  /pulls/comments    every inline review comment (asc, since)
  events           /issues/events     every timeline event (newest first, no since)

plus PR details that REST has no listing of, fetched with batched GraphQL
for each PR whose `updated_at` changed: reviews (with bodies), commits and
changed files.

Each ascending stream re-reads OVERLAP before its cursor, so anything an
earlier run missed (equal timestamps, a briefly stale API, updates during
paging) is picked up. The cursor advances page by page, so an interrupted
run resumes where it stopped. The first page carries the last ETag, so an
unchanged stream costs one free 304.

`check_counts` compares the comment counts GitHub reports per item with
what's stored and refetches the items that differ; `reconcile` compares
the full list of issue and PR numbers and refetches or marks what's off.
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from . import paths
from .github import NotFound, PaginationLimit

OVERLAP = timedelta(days=1)
PER_PAGE = 100
PR_BATCH = 20          # PRs per GraphQL details query
NESTED = 100           # first page of each nested GraphQL connection

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  repo TEXT NOT NULL,
  number INTEGER NOT NULL,
  is_pr INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  gone TEXT,                    -- NULL, 'deleted' or 'transferred' (found by reconcile)
  json TEXT NOT NULL,           -- REST issue object
  PRIMARY KEY (repo, number)
);
CREATE TABLE IF NOT EXISTS issue_comments (
  repo TEXT NOT NULL,
  id INTEGER NOT NULL,
  number INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  json TEXT NOT NULL,
  PRIMARY KEY (repo, id)
);
CREATE INDEX IF NOT EXISTS issue_comments_number ON issue_comments(repo, number);
CREATE TABLE IF NOT EXISTS review_comments (
  repo TEXT NOT NULL,
  id INTEGER NOT NULL,
  number INTEGER NOT NULL,
  review_id INTEGER,
  updated_at TEXT NOT NULL,
  json TEXT NOT NULL,
  PRIMARY KEY (repo, id)
);
CREATE INDEX IF NOT EXISTS review_comments_number ON review_comments(repo, number);
CREATE TABLE IF NOT EXISTS events (
  repo TEXT NOT NULL,
  id INTEGER NOT NULL,
  number INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  json TEXT NOT NULL,
  PRIMARY KEY (repo, id)
);
CREATE INDEX IF NOT EXISTS events_number ON events(repo, number);
CREATE TABLE IF NOT EXISTS pr_details (
  repo TEXT NOT NULL,
  number INTEGER NOT NULL,
  item_updated_at TEXT NOT NULL, -- the item's updated_at these details are current for
  fetched_at TEXT NOT NULL,
  json TEXT NOT NULL,            -- GraphQL PullRequest node, connections completed
  PRIMARY KEY (repo, number)
);
CREATE TABLE IF NOT EXISTS item_events (
  -- items whose events were fetched one by one (fallback when the repo-wide
  -- events listing can't be paged back far enough)
  repo TEXT NOT NULL,
  number INTEGER NOT NULL,
  item_updated_at TEXT NOT NULL,
  PRIMARY KEY (repo, number)
);
CREATE TABLE IF NOT EXISTS cursors (
  repo TEXT NOT NULL,
  stream TEXT NOT NULL,
  cursor TEXT,                  -- newest updated_at (created_at for events) stored
  etag TEXT,                    -- ETag of the first page requested with `since_used`
  since_used TEXT,
  floor TEXT,                   -- events only: oldest created_at the listing reached, '' = all
  PRIMARY KEY (repo, stream)
);
CREATE TABLE IF NOT EXISTS users (
  login TEXT PRIMARY KEY,
  fetched_at TEXT NOT NULL,
  json TEXT NOT NULL
);
"""

ASCENDING = {
    "items": ("/repos/{repo}/issues", {"state": "all", "sort": "updated", "direction": "asc"}),
    "issue_comments": ("/repos/{repo}/issues/comments", {"sort": "updated", "direction": "asc"}),
    "review_comments": ("/repos/{repo}/pulls/comments", {"sort": "updated", "direction": "asc"}),
}


def connect(path=None):
    db = sqlite3.connect(path or paths.raw_db())
    db.executescript(SCHEMA)
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
    return json.dumps(obj, separators=(",", ":"))


# --- storing ---------------------------------------------------------------

def store(db, repo, stream, obj):
    """Upsert one REST object of `stream`. Returns its sort timestamp."""
    if stream == "items":
        db.execute("INSERT OR REPLACE INTO items (repo, number, is_pr, updated_at, gone, json) VALUES (?,?,?,?,NULL,?)",
                   (repo, obj["number"], int("pull_request" in obj), obj["updated_at"], _dump(obj)))
        return obj["updated_at"]
    if stream == "issue_comments":
        db.execute("INSERT OR REPLACE INTO issue_comments VALUES (?,?,?,?,?)",
                   (repo, obj["id"], _tail_number(obj["issue_url"]), obj["updated_at"], _dump(obj)))
        return obj["updated_at"]
    if stream == "review_comments":
        db.execute("INSERT OR REPLACE INTO review_comments VALUES (?,?,?,?,?,?)",
                   (repo, obj["id"], _tail_number(obj["pull_request_url"]), obj.get("pull_request_review_id"),
                    obj["updated_at"], _dump(obj)))
        return obj["updated_at"]
    if stream == "events":
        number = (obj.get("issue") or {}).get("number")
        if number is None:
            return obj["created_at"]
        db.execute("INSERT OR REPLACE INTO events VALUES (?,?,?,?,?)",
                   (repo, obj["id"], number, obj["created_at"], _dump(obj)))
        return obj["created_at"]
    raise ValueError(stream)


def _cursor(db, repo, stream):
    row = db.execute("SELECT cursor, etag, since_used, floor FROM cursors WHERE repo=? AND stream=?",
                     (repo, stream)).fetchone()
    return row or (None, None, None, None)


def _save_cursor(db, repo, stream, cursor, etag, since_used, floor=None):
    db.execute("INSERT OR REPLACE INTO cursors VALUES (?,?,?,?,?,?)",
               (repo, stream, cursor, etag, since_used, floor))
    db.commit()


# --- the ascending streams -------------------------------------------------

def sync_ascending(client, db, repo, stream, log=print):
    """Fetch everything in `stream` updated since the cursor (minus OVERLAP)."""
    path, base = ASCENDING[stream]
    path = path.format(repo=repo)
    cursor, etag, since_used, _ = _cursor(db, repo, stream)
    since = _fmt(_parse(cursor) - OVERLAP) if cursor else None
    params = dict(base, per_page=PER_PAGE)
    if since:
        params["since"] = since
    resp = client.rest(path, params, etag=etag if since_used == since else None)
    if resp.status == 304:
        log(f"{repo} {stream}: unchanged")
        return 0
    first_etag = resp.etag
    newest = cursor
    stored = 0
    while True:
        for obj in resp.data:
            ts = store(db, repo, stream, obj)
            newest = max(newest or ts, ts)
            stored += 1
        db.commit()
        # Save progress after every page so an interrupted run resumes here.
        _save_cursor(db, repo, stream, newest, None, None)
        if not resp.next:
            break
        try:
            resp = client.rest(resp.next)
        except PaginationLimit:
            # Too deep: restart from what we've reached. `since` is inclusive,
            # so the boundary items come again and are harmlessly re-stored.
            if newest == params.get("since"):
                raise
            log(f"{repo} {stream}: pagination limit, restarting from {newest}")
            params["since"] = newest
            resp = client.rest(path, params)
    _save_cursor(db, repo, stream, newest, first_etag, since)
    log(f"{repo} {stream}: stored {stored}")
    return stored


# --- events ----------------------------------------------------------------

def sync_events(client, db, repo, log=print):
    """Repo-wide events, newest first, until OVERLAP before the cursor.

    If GitHub won't page back to the start of history (first run), the
    oldest event reached is recorded as `floor`, and fetch_item_events()
    covers older items one at a time.
    """
    cursor, etag, since_used, floor = _cursor(db, repo, "events")
    stop = _fmt(_parse(cursor) - OVERLAP) if cursor else None
    path = f"/repos/{repo}/issues/events"
    resp = client.rest(path, {"per_page": PER_PAGE}, etag=etag if cursor else None)
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
            store(db, repo, "events", obj)
            newest = max(newest or ts, ts)
            oldest = min(oldest or ts, ts)
            stored += 1
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
    if cursor is None:  # first run: how far back did we get?
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
        "WHERE i.repo = ? AND i.gone IS NULL AND json_extract(i.json, '$.created_at') < ? "
        "AND (e.item_updated_at IS NULL OR e.item_updated_at != i.updated_at)",
        (repo, floor)).fetchall()
    for number, updated in todo:
        for obj in _all_pages(client, f"/repos/{repo}/issues/{number}/events"):
            obj.setdefault("issue", {"number": number})
            store(db, repo, "events", obj)
        db.execute("INSERT OR REPLACE INTO item_events VALUES (?,?,?)", (repo, number, updated))
        db.commit()
    if todo:
        log(f"{repo} events: fetched per-item events for {len(todo)} older items")
    return len(todo)


def _all_pages(client, path, params=None):
    resp = client.rest(path, dict(params or {}, per_page=PER_PAGE))
    while True:
        yield from resp.data
        if not resp.next:
            return
        resp = client.rest(resp.next)


# --- PR details (GraphQL) --------------------------------------------------

ACTOR = "__typename login"

CONNECTIONS = {
    "reviews": f"""
      databaseId
      author {{ {ACTOR} }}
      authorAssociation
      state
      createdAt
      submittedAt
      body
      comments {{ totalCount }}
    """,
    "commits": """
      commit {
        oid
        authoredDate
        committedDate
        message
        parents { totalCount }
        author { name email user { login } }
        committer { name email user { login } }
      }
    """,
    "files": """
      path
      additions
      deletions
      changeType
    """,
}

PR_FIELDS = f"""
  number
  updatedAt
  state
  isDraft
  createdAt
  closedAt
  mergedAt
  mergedBy {{ {ACTOR} }}
  author {{ {ACTOR} }}
  baseRefName
  headRefName
  headRepository {{ nameWithOwner }}
  additions
  deletions
  changedFiles
""" + "".join(
    f"  {name}(first: {NESTED}) {{ totalCount pageInfo {{ hasNextPage endCursor }} nodes {{ {fields} }} }}\n"
    for name, fields in CONNECTIONS.items())

RATE = "rateLimit { cost remaining resetAt }"


def details_query(numbers):
    parts = [f"p{n}: pullRequest(number: {n}) {{ {PR_FIELDS} }}" for n in numbers]
    return ("query($owner: String!, $name: String!) { repository(owner: $owner, name: $name) { "
            + " ".join(parts) + f" }} {RATE} }}")


def more_query(connection):
    return f"""
query($owner: String!, $name: String!, $number: Int!, $after: String) {{
  repository(owner: $owner, name: $name) {{
    pullRequest(number: $number) {{
      {connection}(first: 100, after: $after) {{
        pageInfo {{ hasNextPage endCursor }}
        nodes {{ {CONNECTIONS[connection]} }}
      }}
    }}
  }}
  {RATE}
}}"""


def _complete(client, repo, pr):
    owner, name = repo.split("/")
    for connection in CONNECTIONS:
        conn = pr[connection]
        while conn["pageInfo"]["hasNextPage"]:
            more = client.query(more_query(connection), {
                "owner": owner, "name": name, "number": pr["number"],
                "after": conn["pageInfo"]["endCursor"]})["repository"]["pullRequest"][connection]
            conn["nodes"].extend(more["nodes"])
            conn["pageInfo"] = more["pageInfo"]
    return pr


def stale_prs(db, repo):
    return db.execute(
        "SELECT i.number, i.updated_at FROM items i LEFT JOIN pr_details d "
        "ON d.repo = i.repo AND d.number = i.number "
        "WHERE i.repo = ? AND i.is_pr = 1 AND i.gone IS NULL "
        "AND (d.item_updated_at IS NULL OR d.item_updated_at != i.updated_at) ORDER BY i.number",
        (repo,)).fetchall()


def sync_pr_details(client, db, repo, log=print):
    """Refetch reviews, commits and files for every PR that changed."""
    owner, name = repo.split("/")
    todo = stale_prs(db, repo)
    for i in range(0, len(todo), PR_BATCH):
        batch = todo[i:i + PR_BATCH]
        data = client.query(details_query([n for n, _ in batch]), {"owner": owner, "name": name})["repository"]
        for number, updated in batch:
            pr = data.get(f"p{number}")
            if pr is None:  # deleted since it was listed; reconcile will mark it
                continue
            _complete(client, repo, pr)
            db.execute("INSERT OR REPLACE INTO pr_details VALUES (?,?,?,?,?)",
                       (repo, number, updated, now(), _dump(pr)))
        db.commit()
    if todo:
        log(f"{repo} pr_details: refreshed {len(todo)}")
    return len(todo)


# --- consistency checks ------------------------------------------------------

def comment_mismatches(db, repo):
    """Items whose stored comments don't match the counts GitHub reports."""
    issue = db.execute(
        "SELECT i.number FROM items i WHERE i.repo = ? AND i.gone IS NULL AND "
        "json_extract(i.json, '$.comments') != "
        "(SELECT COUNT(*) FROM issue_comments c WHERE c.repo = i.repo AND c.number = i.number)",
        (repo,)).fetchall()
    review = db.execute(
        "SELECT d.number, d.json FROM pr_details d JOIN items i ON i.repo = d.repo AND i.number = d.number "
        "WHERE d.repo = ? AND i.gone IS NULL", (repo,)).fetchall()
    stored = dict(db.execute("SELECT number, COUNT(*) FROM review_comments WHERE repo = ? GROUP BY number",
                             (repo,)).fetchall())
    review_bad = []
    for number, js in review:
        pr = json.loads(js)
        expected = sum(r["comments"]["totalCount"] for r in pr["reviews"]["nodes"])
        if expected != stored.get(number, 0):
            review_bad.append(number)
    return [n for (n,) in issue], review_bad


def check_counts(client, db, repo, log=print):
    """Refetch the comments of items whose stored counts are off. This also
    drops comments that were deleted on GitHub."""
    issue_bad, review_bad = comment_mismatches(db, repo)
    for number in issue_bad:
        _replace(db, repo, "issue_comments", number, _all_pages(client, f"/repos/{repo}/issues/{number}/comments"))
    for number in review_bad:
        _replace(db, repo, "review_comments", number, _all_pages(client, f"/repos/{repo}/pulls/{number}/comments"))
    if issue_bad or review_bad:
        log(f"{repo}: refetched comments for {len(issue_bad)} items and review comments for {len(review_bad)} PRs")
    return issue_bad, review_bad


def _replace(db, repo, stream, number, objs):
    objs = list(objs)
    db.execute(f"DELETE FROM {stream} WHERE repo = ? AND number = ?", (repo, number))
    for obj in objs:
        store(db, repo, stream, obj)
    db.commit()


INDEX_QUERY = """
query($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    %s(first: 100, after: $after) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes { number updatedAt }
    }
  }
  rateLimit { cost remaining resetAt }
}"""


def reconcile(client, db, repo, log=print):
    """Compare every issue and PR number on GitHub with what's stored.

    Refetches items that are missing or out of date, marks items that are
    gone (deleted or transferred), and returns a report. It's run weekly,
    and is cheap: only numbers and timestamps are listed.
    """
    owner, name = repo.split("/")
    remote, total = {}, 0
    for conn in ("issues", "pullRequests"):
        after = None
        while True:
            page = client.query(INDEX_QUERY % conn, {"owner": owner, "name": name, "after": after})["repository"][conn]
            for node in page["nodes"]:
                remote[node["number"]] = node["updatedAt"]
            if not page["pageInfo"]["hasNextPage"]:
                total += page["totalCount"]
                break
            after = page["pageInfo"]["endCursor"]
    local = dict(db.execute("SELECT number, updated_at FROM items WHERE repo = ? AND gone IS NULL", (repo,)))
    stale = sorted(n for n, u in remote.items() if local.get(n) is None or local[n] < u)
    missing_remotely = sorted(set(local) - set(remote))
    for number in stale:
        try:
            store(db, repo, "items", client.rest(f"/repos/{repo}/issues/{number}").data)
        except NotFound:
            pass
    for number in missing_remotely:
        try:
            obj = client.rest(f"/repos/{repo}/issues/{number}").data
            gone = None if obj["repository_url"].lower().endswith("/repos/" + repo.lower()) else "transferred"
        except NotFound:
            gone = "deleted"
        if gone:
            db.execute("UPDATE items SET gone = ? WHERE repo = ? AND number = ?", (gone, repo, number))
    db.commit()
    stored = db.execute("SELECT COUNT(*) FROM items WHERE repo = ? AND gone IS NULL", (repo,)).fetchone()[0]
    report = {"repo": repo, "remote_total": total, "stored": stored,
              "refetched": stale, "gone": missing_remotely}
    log(f"{repo} reconcile: GitHub has {total}, stored {stored}, refetched {len(stale)}, "
        f"checked {len(missing_remotely)} missing")
    return report


# --- whole repo ----------------------------------------------------------------

def sync_repo(client, db, repo, log=print):
    for stream in ASCENDING:
        sync_ascending(client, db, repo, stream, log=log)
    sync_events(client, db, repo, log=log)
    fetch_item_events(client, db, repo, log=log)
    sync_pr_details(client, db, repo, log=log)
    check_counts(client, db, repo, log=log)


# --- users -----------------------------------------------------------------------

USER_FIELDS = "login name company location websiteUrl"


def seen_logins(db):
    """Logins of every human account that appears anywhere in the raw data."""
    logins = set()

    def add(user):
        if user and user.get("login") and user.get("type", "User") == "User" \
                and user.get("__typename", "User") == "User":
            logins.add(user["login"])

    for table, keys in (("items", ("user", "closed_by")), ("issue_comments", ("user",)),
                        ("review_comments", ("user",)), ("events", ("actor",))):
        for (js,) in db.execute(f"SELECT json FROM {table}"):
            obj = json.loads(js)
            for k in keys:
                add(obj.get(k))
    for (js,) in db.execute("SELECT json FROM pr_details"):
        pr = json.loads(js)
        add(pr.get("mergedBy"))
        for r in pr["reviews"]["nodes"]:
            add(r.get("author"))
    return logins


def users_to_fetch(db):
    have = {r[0] for r in db.execute("SELECT login FROM users")}
    return sorted(seen_logins(db) - have)


def extract_users(client, db, logins, batch=50, log=print):
    """Fetch public profiles (name, company) for `logins`, `batch` per query."""
    for i in range(0, len(logins), batch):
        chunk = logins[i:i + batch]
        parts = [f'u{j}: user(login: {json.dumps(login)}) {{ {USER_FIELDS} }}' for j, login in enumerate(chunk)]
        data = client.query("query { " + " ".join(parts) + f" {RATE} }}")
        for j, login in enumerate(chunk):
            profile = data.get(f"u{j}") or {"login": login, "missing": True}
            db.execute("INSERT OR REPLACE INTO users VALUES (?,?,?)", (login, now(), json.dumps(profile)))
        db.commit()
        log(f"users: {min(i + batch, len(logins))}/{len(logins)}")
