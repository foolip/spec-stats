"""Build data/private/derived.sqlite from the files in data/github/ (offline).

One row per action, each attributed to an account and an organization at
the time it happened (docs/maintenance-load.md):

- review:          a review submitted on someone else's PR
- review_comment:  an inline review comment on someone else's PR
- merge:           merging a PR (`detail` is 'self' or 'other')
- comment:         a conversation comment on someone else's issue or PR
- pr:              authoring a PR that was merged (counted at merge time)
- issue:           opening an issue

Bots, self-actions and generated boilerplate comments are left out;
deleted accounts are kept as "ghost". Everything comes from the REST
objects stored by specstats/extract.py.
"""

import json
import sqlite3
from collections import defaultdict

from . import extract, paths
from .orgs import Attributor

SCHEMA = """
DROP TABLE IF EXISTS actions;
CREATE TABLE actions (
  repo TEXT NOT NULL,
  kind TEXT NOT NULL,           -- 'pr' or 'issue': what it was on
  number INTEGER NOT NULL,
  action TEXT NOT NULL,
  login TEXT NOT NULL,
  org TEXT NOT NULL,
  at TEXT NOT NULL,             -- ISO timestamp (UTC)
  month TEXT NOT NULL,          -- YYYY-MM
  detail TEXT                   -- review state; 'self'/'other' for merges
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
  ready_at TEXT NOT NULL,       -- created_at, or first ready-for-review for PRs opened as drafts
  closed_at TEXT,
  merged_at TEXT,
  first_response_at TEXT,       -- first review, review comment or comment by someone else (not a bot)
  first_response_by TEXT,
  labels TEXT NOT NULL,         -- JSON array
  PRIMARY KEY (repo, kind, number)
);
"""

BOILERPLATE = ("is programmatically generated",)


def rest_login(user):
    if not user:
        return "ghost", None
    return user.get("login") or "ghost", "Bot" if user.get("type") == "Bot" else "User"


def is_boilerplate(body):
    return any(b in (body or "") for b in BOILERPLATE)


def derive(root=None, out_path=None, attr=None):
    if attr is None:
        attr = Attributor(extract.load_profiles(root))
    out = sqlite3.connect(out_path or paths.derived_db())
    out.executescript(SCHEMA)

    stores = {repo: extract.RepoStore(repo, root) for repo in extract.stored_repos(root)}
    items = {}
    ready = {}
    for repo, store in stores.items():
        for p in store.dir.glob("issues/*.json"):
            obj = extract.read_json(p)
            items[(repo, obj["number"])] = ("pull_request" in obj, obj)
        for number, events in store.lists("issues", "events"):
            times = [e["created_at"] for e in events if e.get("event") == "ready_for_review"]
            if times:
                ready[(repo, number)] = min(times)

    actions = []
    responses = defaultdict(list)  # (repo, number) -> [(at, login)]

    def act(repo, number, action, login, at, detail=None):
        is_pr = items[(repo, number)][0]
        actions.append((repo, "pr" if is_pr else "issue", number, action, login,
                        attr.org(login, at), at, at[:7], detail))

    authors = {}
    for (repo, number), (is_pr, obj) in items.items():
        author, typ = rest_login(obj.get("user"))
        authors[(repo, number)] = author
        if attr.is_bot(author, typ):
            continue
        if not is_pr:
            act(repo, number, "issue", author, obj["created_at"])
        elif (obj.get("pull_request") or {}).get("merged_at"):
            act(repo, number, "pr", author, obj["pull_request"]["merged_at"])

    for repo, store in stores.items():
        for p in store.dir.glob("pulls/*.json"):
            pr = extract.read_json(p)
            number = pr["number"]
            if (repo, number) not in items or not pr.get("merged_at"):
                continue
            merger, typ = rest_login(pr.get("merged_by"))
            if not attr.is_bot(merger, typ):
                act(repo, number, "merge", merger, pr["merged_at"],
                    "self" if merger == authors[(repo, number)] else "other")

        for number, reviews in store.lists("pulls", "reviews"):
            if (repo, number) not in items:
                continue
            for review in reviews:
                login, typ = rest_login(review.get("user"))
                at = review.get("submitted_at")
                if (not at or review.get("state") == "PENDING" or login == authors[(repo, number)]
                        or attr.is_bot(login, typ)):
                    continue
                act(repo, number, "review", login, at, review.get("state"))
                responses[(repo, number)].append((at, login))

        for kind, action in (("issues", "comment"), ("pulls", "review_comment")):
            for number, comments in store.lists(kind, "comments"):
                if (repo, number) not in items:
                    continue
                for c in comments:
                    login, typ = rest_login(c.get("user"))
                    if login == authors[(repo, number)] or attr.is_bot(login, typ) or is_boilerplate(c.get("body")):
                        continue
                    act(repo, number, action, login, c["created_at"])
                    responses[(repo, number)].append((c["created_at"], login))

    out.executemany("INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?)", actions)

    rows = []
    for (repo, number), (is_pr, obj) in items.items():
        author = authors[(repo, number)]
        ready_at = ready.get((repo, number), obj["created_at"]) if is_pr else obj["created_at"]
        later = sorted(r for r in responses[(repo, number)] if r[0] >= ready_at)
        first_at, first_by = later[0] if later else (None, None)
        merged = (obj.get("pull_request") or {}).get("merged_at")
        rows.append((repo, "pr" if is_pr else "issue", number, author, attr.org(author, obj["created_at"]),
                     "merged" if merged else obj["state"], obj["created_at"], ready_at, obj.get("closed_at"),
                     merged, first_at, first_by, json.dumps([l["name"] for l in obj.get("labels", [])])))
    out.executemany("INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    out.commit()
    return len(rows)
