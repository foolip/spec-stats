"""config/repos.txt from whatwg/sg's db.json (`python3 -m specstats repos`).

db.json lists the WHATWG's Living Standards by workstream, each with its
URL, https://{shortname}.spec.whatwg.org/; its repo is whatwg/{shortname}.
The file lists every one of them, sorted. Which lines are commented out is
kept: only the repos already fetched stay uncommented, and new ones come in
commented out, so updating the list never starts fetching anything. A
fetched repo that's no longer in db.json stays, marked as such.

One request, to raw.githubusercontent.com (no token or API quota needed).
"""

import json
import re
import urllib.request

from . import github, paths

DB_URL = "https://raw.githubusercontent.com/whatwg/sg/main/db.json"
# A repo's line, commented out or not.
ENTRY = re.compile(r"^#?[ \t]*(whatwg/[\w.-]+)[ \t]*(?:#.*)?$", re.M)
HREF = re.compile(r"https://([a-z0-9-]+)\.spec\.whatwg\.org/")

HEADER = """\
# WHATWG Living Standards, one GitHub repo per line: whatwg/{shortname} for
# each standard in whatwg/sg's db.json (https://github.com/whatwg/sg).
# Written by `python3 -m specstats repos`, which keeps which lines are
# commented out. Only uncommented repos are fetched, in this order; new
# ones come in commented out. docs/plan.md says which are fetched and why.
"""


def fetch_db():
    req = urllib.request.Request(DB_URL, headers={"User-Agent": github.USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def from_db(db):
    """The repos of db.json's standards, sorted."""
    out = set()
    for ws in db["workstreams"]:
        for std in ws["standards"]:
            m = HREF.match(std["href"])
            if not m:
                raise ValueError(f"no whatwg/ repo for {std['name']}: {std['href']}")
            out.add(f"whatwg/{m.group(1)}")
    if not out:
        raise ValueError("db.json lists no standards")
    return sorted(out)


def render(repos, enabled):
    """The file: every repo in `repos`, commented out unless in `enabled`;
    then those in `enabled` that aren't in `repos`."""
    lines = [r if r in enabled else f"# {r}" for r in repos]
    lines += [f"{r}  # not in db.json" for r in enabled if r not in repos]
    return HEADER + "\n".join(lines) + "\n"


def update(db=None, path=None, log=print):
    """Rewrite config/repos.txt from db.json. Returns whether it changed."""
    path = path or paths.CONFIG / "repos.txt"
    db = db if db is not None else fetch_db()
    repos = from_db(db)
    old = path.read_text() if path.exists() else ""
    enabled = paths.parse_repos(old)
    listed = set(ENTRY.findall(old))
    for r in repos:
        if r not in listed:
            log(f"new: {r} (commented out)")
    for r in sorted(listed - set(repos)):
        log(f"not in db.json: {r}" + (" (kept, as it's fetched)" if r in enabled else " (removed)"))
    text = render(repos, enabled)
    log(f"{len(repos)} standards' repos; fetched: {', '.join(paths.parse_repos(text)) or 'none'}")
    if text == old:
        log(f"{path.name} is up to date")
        return False
    path.write_text(text)
    log(f"wrote {path}")
    return True
