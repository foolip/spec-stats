"""Fetch pull requests, issues and the users behind them from GitHub.

Raw responses are kept losslessly in data/private/raw.sqlite, one row per
PR or issue (the whole GraphQL node, nested connections completed), so
everything downstream can be rebuilt offline.

Fetching is incremental: PRs and issues are listed newest-updated first,
and listing stops at the first node that hasn't changed since the last run.
"""

import json
import sqlite3
from datetime import datetime, timezone

from . import paths

PAGE = 25          # top-level nodes per page (nested connections make pages costly)
NESTED = 50        # first page of each nested connection
NESTED_MORE = 100  # follow-up pages of a nested connection

ACTOR = "author { __typename login }"

REVIEW_FIELDS = f"""
  {ACTOR}
  state
  submittedAt
  body
  comments {{ totalCount }}
"""

COMMENT_FIELDS = f"""
  {ACTOR}
  createdAt
  body
"""

PR_FIELDS = f"""
  number
  title
  url
  state
  isDraft
  createdAt
  updatedAt
  closedAt
  mergedAt
  {ACTOR}
  mergedBy {{ __typename login }}
  additions
  deletions
  changedFiles
  body
  labels(first: 30) {{ nodes {{ name }} }}
  reviews(first: {NESTED}) {{
    pageInfo {{ hasNextPage endCursor }}
    nodes {{ {REVIEW_FIELDS} }}
  }}
  comments(first: {NESTED}) {{
    pageInfo {{ hasNextPage endCursor }}
    nodes {{ {COMMENT_FIELDS} }}
  }}
"""

ISSUE_FIELDS = f"""
  number
  title
  url
  state
  stateReason
  createdAt
  updatedAt
  closedAt
  {ACTOR}
  body
  labels(first: 30) {{ nodes {{ name }} }}
  comments(first: {NESTED}) {{
    pageInfo {{ hasNextPage endCursor }}
    nodes {{ {COMMENT_FIELDS} }}
  }}
"""

KINDS = {
    "pr": ("pullRequests", "pullRequest", PR_FIELDS, {"reviews": REVIEW_FIELDS, "comments": COMMENT_FIELDS}),
    "issue": ("issues", "issue", ISSUE_FIELDS, {"comments": COMMENT_FIELDS}),
}

RATE = "rateLimit { cost remaining resetAt }"

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
  repo TEXT NOT NULL,
  kind TEXT NOT NULL,           -- 'pr' or 'issue'
  number INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  json TEXT NOT NULL,
  PRIMARY KEY (repo, kind, number)
);
CREATE TABLE IF NOT EXISTS sync (
  repo TEXT NOT NULL,
  kind TEXT NOT NULL,
  high_water TEXT NOT NULL,     -- newest updatedAt fully fetched
  floor TEXT,                   -- oldest updatedAt reached (for --since backfills)
  PRIMARY KEY (repo, kind)
);
CREATE TABLE IF NOT EXISTS users (
  login TEXT PRIMARY KEY,
  fetched_at TEXT NOT NULL,
  json TEXT NOT NULL
);
"""


def connect(path=None):
    db = sqlite3.connect(path or paths.raw_db())
    db.executescript(SCHEMA)
    return db


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def list_query(kind):
    conn, _, fields, _ = KINDS[kind]
    return f"""
query($owner: String!, $name: String!, $after: String) {{
  repository(owner: $owner, name: $name) {{
    {conn}(first: {PAGE}, after: $after, orderBy: {{field: UPDATED_AT, direction: DESC}}) {{
      pageInfo {{ hasNextPage endCursor }}
      nodes {{ {fields} }}
    }}
  }}
  {RATE}
}}"""


def nested_query(kind, connection):
    _, single, _, nested = KINDS[kind]
    return f"""
query($owner: String!, $name: String!, $number: Int!, $after: String) {{
  repository(owner: $owner, name: $name) {{
    {single}(number: $number) {{
      {connection}(first: {NESTED_MORE}, after: $after) {{
        pageInfo {{ hasNextPage endCursor }}
        nodes {{ {nested[connection]} }}
      }}
    }}
  }}
  {RATE}
}}"""


def complete_node(client, repo, kind, node):
    """Fetch the rest of any nested connection that didn't fit in one page."""
    owner, name = repo.split("/")
    _, single, _, nested = KINDS[kind]
    for connection in nested:
        conn = node.get(connection)
        if not conn:
            continue
        while conn["pageInfo"]["hasNextPage"]:
            data = client.query(nested_query(kind, connection), {
                "owner": owner, "name": name, "number": node["number"],
                "after": conn["pageInfo"]["endCursor"],
            })
            more = data["repository"][single][connection]
            conn["nodes"].extend(more["nodes"])
            conn["pageInfo"] = more["pageInfo"]
    return node


def extract_repo(client, db, repo, kind, since=None, log=print):
    """Fetch every PR/issue of `repo` updated since the last run.

    `since` (ISO date) bounds the first run, or takes an earlier run further
    back. Nodes already stored with the same updatedAt are not refetched.
    Returns the number of nodes stored.
    """
    owner, name = repo.split("/")
    conn_name = KINDS[kind][0]
    row = db.execute("SELECT high_water, floor FROM sync WHERE repo=? AND kind=?", (repo, kind)).fetchone()
    high_water, floor = row if row else (None, None)
    # floor "" means the whole history is stored.
    backfill = high_water is None or (since is not None and floor != "" and since < floor)
    after = None
    stored = 0
    newest = None
    stop_reason = "end"
    while True:
        data = client.query(list_query(kind), {"owner": owner, "name": name, "after": after})
        page = data["repository"][conn_name]
        for node in page["nodes"]:
            updated = node["updatedAt"]
            newest = newest or updated
            if since and updated < since:
                stop_reason = "since"
                break
            if not backfill and updated <= high_water:
                stop_reason = "high_water"
                break
            prev = db.execute("SELECT updated_at FROM nodes WHERE repo=? AND kind=? AND number=?",
                              (repo, kind, node["number"])).fetchone()
            if prev and prev[0] == updated:
                continue
            complete_node(client, repo, kind, node)
            db.execute(
                "INSERT OR REPLACE INTO nodes (repo, kind, number, updated_at, fetched_at, json) "
                "VALUES (?,?,?,?,?,?)",
                (repo, kind, node["number"], updated, now(), json.dumps(node, separators=(",", ":"))))
            stored += 1
        db.commit()
        if stop_reason != "end" or not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    if newest is not None:
        new_high = max(newest, high_water or newest)
        if stop_reason == "end":
            new_floor = ""
        elif stop_reason == "since":
            new_floor = since if floor is None else min(since, floor)
        else:
            new_floor = floor
        db.execute("INSERT OR REPLACE INTO sync (repo, kind, high_water, floor) VALUES (?,?,?,?)",
                   (repo, kind, new_high, new_floor))
        db.commit()
    log(f"{repo} {kind}: stored {stored} (requests so far: {client.requests})")
    return stored


USER_QUERY_FIELDS = "login name company location websiteUrl"


def users_to_fetch(db):
    seen = {r[0] for r in db.execute("SELECT login FROM users")}
    logins = set()
    for (js,) in db.execute("SELECT json FROM nodes"):
        for actor in iter_actors(json.loads(js)):
            if actor.get("__typename") == "User" and actor.get("login"):
                logins.add(actor["login"])
    return sorted(logins - seen)


def iter_actors(node):
    for key in ("author", "mergedBy"):
        if node.get(key):
            yield node[key]
    for conn in ("reviews", "comments"):
        for child in (node.get(conn) or {}).get("nodes", []):
            if child.get("author"):
                yield child["author"]


def extract_users(client, db, logins, batch=50, log=print):
    """Fetch public profiles (name, company) for `logins`, `batch` per query."""
    for i in range(0, len(logins), batch):
        chunk = logins[i:i + batch]
        parts = [f'u{j}: user(login: {json.dumps(login)}) {{ {USER_QUERY_FIELDS} }}'
                 for j, login in enumerate(chunk)]
        data = client.query("query { " + " ".join(parts) + f" {RATE} }}")
        for j, login in enumerate(chunk):
            profile = data.get(f"u{j}") or {"login": login, "missing": True}
            db.execute("INSERT OR REPLACE INTO users (login, fetched_at, json) VALUES (?,?,?)",
                       (login, now(), json.dumps(profile)))
        db.commit()
        log(f"users: {min(i + batch, len(logins))}/{len(logins)}")
