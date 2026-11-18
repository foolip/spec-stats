"""whatwg/sg's db.json, the list of the WHATWG's Living Standards.

`python3 -m specstats sync-db` copies it byte for byte into config/db.json
(one request, to raw.githubusercontent.com: no token or API quota needed).
The repos to fetch are read from that copy: each standard's URL is
https://{shortname}.spec.whatwg.org/, and its repo is whatwg/{shortname}.
"""

import json
import re
import urllib.request

from . import github, paths

DB_URL = "https://raw.githubusercontent.com/whatwg/sg/main/db.json"
HREF = re.compile(r"https://([a-z0-9-]+)\.spec\.whatwg\.org/")


def db_path():
    return paths.CONFIG / "db.json"


def standards(db=None):
    """{repo: the standard's name} for db.json's standards, e.g.
    {"whatwg/html": "HTML"}, sorted by repo."""
    if db is None:
        db = json.loads(db_path().read_text())
    out = {}
    for ws in db["workstreams"]:
        for std in ws["standards"]:
            m = HREF.match(std["href"])
            if not m:
                raise ValueError(f"no whatwg/ repo for {std['name']}: {std['href']}")
            out[f"whatwg/{m.group(1)}"] = std["name"]
    if not out:
        raise ValueError("db.json lists no standards")
    return dict(sorted(out.items()))


def repos(db=None):
    """The repos of db.json's standards, sorted."""
    return list(standards(db))


def fetch():
    req = urllib.request.Request(DB_URL, headers={"User-Agent": github.USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def sync(raw=None, path=None, log=print):
    """Copy db.json into config/db.json. Returns whether it changed."""
    path = path or db_path()
    raw = raw if raw is not None else fetch()
    new = repos(json.loads(raw))  # fails, writing nothing, if it isn't usable
    old = repos(json.loads(path.read_bytes())) if path.exists() else []
    for r in new:
        if r not in old:
            log(f"new: {r}")
    for r in old:
        if r not in new:
            log(f"removed: {r} (its stored data stays in data/github/, no longer updated)")
    log(f"{len(new)} standards' repos")
    if path.exists() and path.read_bytes() == raw:
        log(f"{path.name} is up to date")
        return False
    path.write_bytes(raw)
    log(f"wrote {path}")
    return True
