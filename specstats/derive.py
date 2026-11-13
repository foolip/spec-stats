"""Build data/private/derived.sqlite from the raw cache (offline).

One row per maintenance action, each attributed to an account and an
organization at the time it happened:

- review:        a review submitted on someone else's PR
- merge:         merging a PR (mergedBy)
- pr:            authoring a PR that was merged (counted at merge time)
- issue:         opening an issue
- comment:       a conversation comment on someone else's issue or PR

Bots and self-reviews are left out; ghost (deleted) accounts are kept as
"ghost".
"""

import json
import sqlite3

from . import extract, paths
from .orgs import Attributor

SCHEMA = """
DROP TABLE IF EXISTS actions;
CREATE TABLE actions (
  repo TEXT NOT NULL,
  kind TEXT NOT NULL,           -- 'pr' or 'issue': what it was on
  number INTEGER NOT NULL,
  action TEXT NOT NULL,         -- review | merge | pr | issue | comment
  login TEXT NOT NULL,
  org TEXT NOT NULL,
  at TEXT NOT NULL,             -- ISO timestamp (UTC)
  month TEXT NOT NULL,          -- YYYY-MM
  review_state TEXT,            -- APPROVED | CHANGES_REQUESTED | COMMENTED | DISMISSED
  inline_comments INTEGER       -- inline comments in a review
);
CREATE INDEX actions_month ON actions(month, repo, action);
DROP TABLE IF EXISTS items;
CREATE TABLE items (
  repo TEXT NOT NULL,
  kind TEXT NOT NULL,
  number INTEGER NOT NULL,
  author TEXT NOT NULL,
  author_org TEXT NOT NULL,
  state TEXT NOT NULL,
  created_at TEXT NOT NULL,
  closed_at TEXT,
  merged_at TEXT,
  first_response_at TEXT,       -- first review or comment by someone else (not a bot)
  first_response_by TEXT,
  labels TEXT NOT NULL,         -- JSON array
  PRIMARY KEY (repo, kind, number)
);
"""


def login_of(actor):
    if not actor:
        return "ghost", None
    return actor.get("login") or "ghost", actor.get("__typename")


def node_actions(repo, kind, node, attr):
    """Yield action rows for one raw node."""
    author, author_type = login_of(node.get("author"))
    number = node["number"]

    def row(action, login, at, state=None, inline=None):
        return (repo, kind, number, action, login, attr.org(login, at), at, at[:7], state, inline)

    if not attr.is_bot(author, author_type):
        if kind == "issue":
            yield row("issue", author, node["createdAt"])
        elif node.get("mergedAt"):
            yield row("pr", author, node["mergedAt"])
    if kind == "pr" and node.get("mergedAt"):
        merger, merger_type = login_of(node.get("mergedBy"))
        if not attr.is_bot(merger, merger_type):
            yield row("merge", merger, node["mergedAt"])
    for review in (node.get("reviews") or {}).get("nodes", []):
        login, typ = login_of(review.get("author"))
        if login == author or attr.is_bot(login, typ) or not review.get("submittedAt"):
            continue
        yield row("review", login, review["submittedAt"], review.get("state"),
                  (review.get("comments") or {}).get("totalCount", 0))
    for comment in (node.get("comments") or {}).get("nodes", []):
        login, typ = login_of(comment.get("author"))
        if login == author or attr.is_bot(login, typ):
            continue
        yield row("comment", login, comment["createdAt"])


def first_response(node, attr):
    author, _ = login_of(node.get("author"))
    times = []
    for conn, field in (("reviews", "submittedAt"), ("comments", "createdAt")):
        for child in (node.get(conn) or {}).get("nodes", []):
            login, typ = login_of(child.get("author"))
            if login != author and not attr.is_bot(login, typ) and child.get(field):
                times.append((child[field], login))
    return min(times) if times else (None, None)


def derive(raw_path=None, out_path=None, attr=None):
    raw = extract.connect(raw_path)
    if attr is None:
        profiles = {login: json.loads(js) for login, js in raw.execute("SELECT login, json FROM users")}
        attr = Attributor(profiles)
    out = sqlite3.connect(out_path or paths.derived_db())
    out.executescript(SCHEMA)
    n = 0
    for repo, kind, js in raw.execute("SELECT repo, kind, json FROM nodes"):
        node = json.loads(js)
        out.executemany("INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?)", node_actions(repo, kind, node, attr))
        author, _ = login_of(node.get("author"))
        resp_at, resp_by = first_response(node, attr)
        out.execute("INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            repo, kind, node["number"], author, attr.org(author, node["createdAt"]), node["state"],
            node["createdAt"], node.get("closedAt"), node.get("mergedAt"), resp_at, resp_by,
            json.dumps([l["name"] for l in (node.get("labels") or {}).get("nodes", [])])))
        n += 1
    out.commit()
    return n
