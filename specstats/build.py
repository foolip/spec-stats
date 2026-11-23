"""Build the JSON file the site reads, from data/github/ (offline).

`python3 -m specstats build` writes build/data.json (`docs/site-design.md`):

  {"meta": {"from": "2022-01-01", "to": "2026-11-17"},
   "repos": {"name": ["compat", ...], "standard": ["Compatibility", ...]},
   "items": {"repo": [0, ...], "number": [1234, 5, ...], "kind": [2, 0, ...],
             "created": [-412, 3, ...], "closed": [null, 2, ...], "later_in_day": [0, 1, ...]}}

Each table is stored by column. `items.repo` is an index into `repos`.
`repos` is in the order the site lists specs, by `spec_order`, so the
site never sorts them itself. Days count UTC days from `meta.from` (day
0). For each item:

- `kind`: 0 for an issue, 1 for a PR not merged in the window, 2 for a
  PR merged in it.
- `created`: the day of its `created_at`, negative for an item opened
  before the window.
- `closed`: for an item closed at the end of the window, the day of its
  last close, as days after `created`; null for an item open at the end.
  A merged PR's last close is its merge.
- `later_in_day`: 1 if its last close was at a later time of day (UTC)
  than its creation, else 0 (and 0 while it's open). So its time open,
  in whole days rounded up, is `closed + later_in_day`: a limit in whole
  days ("within 1 day") counts it as the exact time would.

An item is open from its creation to its last close, as GitHub search
sees it (`created:<=D (is:open OR closed:>D)`): closes followed by a
reopen are ignored, so every count can be checked against a search.
Drafts count as open PRs, as in a search for `is:pr is:open`. An item
is in the file if it was open on any day of the window by that rule.

The layout is chosen to compress well: `items.number` and
`items.created` are differences from the previous item of the same repo
(the first of each repo's items holds its own value). Items are written
by repo and number, so both are small. The client assumes no order beyond
that.

One timeline: from `updated_since` in config/fetch.json to the last full
UTC day before the newest `updated_at` seen in any repo (each repo's
`items.cursor`), or the last reconcile's start (`items.rows`) if newer:
every run lists every repo, so that's when the data was last complete.
Changes after its end are ignored: an item closed after it is open.

Where an item's events disagree with its state (closed with no `closed`
event, whatwg/fullscreen #220), the item's own state wins: a `closed` at
its `closed_at`, or a `reopened` at its `updated_at`. A merged PR whose
last close isn't its merge is closed at its merge. `check` keeps
reporting the first; the build reports how many it fixed up.
"""

import datetime
import json
from pathlib import Path

from . import extract, paths, sgdb


def spec_order(name):
    """The key specs are listed by: their name, with "Web Foo" as WebFoo,
    so Web IDL is among WebBluetooth, WebHID and the rest."""
    return name.replace("Web ", "Web", 1) if name.startswith("Web ") else name


def out_path():
    return paths.ROOT / "build" / "data.json"


def _day(ts):
    return datetime.date.fromisoformat(ts[:10])


def _time(ts):
    return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def listed(store):
    """Whether the repo's listings are done: its first listing, its listing
    of old open items, and any listing back to a moved start."""
    s = store.state.get("items", {})
    return "cursor" in s and "started" not in s and "extend" not in s and s.get("open") == {"done": True}


def newest(store):
    """The newest time the repo's state shows it was listed at: the newest
    `updated_at` seen (`items.cursor`) or the last reconcile's start
    (`items.rows`)."""
    s = store.state["items"]
    return max(t for t in (s["cursor"], s.get("rows")) if t)


def _fix(fixes, what):
    fixes[what] = fixes.get(what, 0) + 1


def transitions(obj, events, fixes):
    """(time, "closed" or "reopened") for the item's changes of open state,
    in time order, made to agree with the item's own state: a second
    `closed` without a `reopened` between is left out."""
    evs = sorted(events, key=lambda e: (e["created_at"], e["id"]))
    out = []
    is_open = True
    for e in evs:
        if e["event"] in ("closed", "reopened") and is_open == (e["event"] == "closed"):
            is_open = not is_open
            out.append((e["created_at"], e["event"]))
    if is_open != (obj["state"] == "open"):
        if obj["state"] == "closed":
            out.append((obj["closed_at"], "closed"))
            _fix(fixes, "closed with no `closed` event")
        else:
            out.append((obj["updated_at"], "reopened"))
            _fix(fixes, "open after a `closed` event")
        out.sort(key=lambda t: t[0])
    return out


def item_row(obj, events, start, end, fixes):
    """(kind, time of the last close or None if open) for one issue or PR
    as of the end of the window, `start` and `end` as dates with `end`
    excluded; None if it wasn't open on any day of the window."""
    if _day(obj["created_at"]) >= end:
        return None
    last_close = None
    for at, kind in transitions(obj, events, fixes):
        if _day(at) >= end:
            break
        last_close = at if kind == "closed" else None
    merged_at = (obj.get("pull_request") or {}).get("merged_at")
    if merged_at and _day(merged_at) < end:
        if last_close is None or _day(last_close) != _day(merged_at):
            _fix(fixes, "merged, but its last close isn't the merge: closed at the merge")
            last_close = merged_at
        kind = 2
    else:
        kind = 1 if "pull_request" in obj else 0
    if last_close is not None and _day(last_close) < start:
        return None  # closed for the whole window
    return kind, last_close


def build(root=None, standards=None, updated_since=None, log=print):
    """The site's data, as a dict."""
    standards = standards if standards is not None else sgdb.standards()
    since = updated_since or extract.load_updated_since()
    start = _day(since)
    stores = {}
    for repo in sorted(standards, key=lambda r: (spec_order(standards[r]), r)):
        store = extract.RepoStore(repo, root)
        if not store.state:
            log(f"{repo}: nothing stored; left out")
        elif store.state.get("items", {}).get("from") != since:
            log(f"{repo}: stored from {store.state.get('items', {}).get('from')}, not {since}; left out")
        elif not listed(store):
            log(f"{repo}: no complete listing yet; left out")
        else:
            stores[repo] = store
    if not stores:
        raise ValueError("no repo has complete data")
    # Every run lists every repo, so the newest time seen anywhere is when
    # the data was last complete. Its own day is partial.
    end = max(_day(newest(s)) for s in stores.values())
    to = end - datetime.timedelta(days=1)

    repos = {"name": [], "standard": []}
    items = {"repo": [], "number": [], "kind": [], "created": [], "closed": [], "later_in_day": []}
    fixes = {}
    for r, (repo, store) in enumerate(stores.items()):
        repos["name"].append(repo.split("/", 1)[1])
        repos["standard"].append(standards[repo])
        index = store.index()
        last_number = last_created = 0  # of the repo's previous item
        for number in sorted(n for n in index if store.full(n)):
            obj = store.get("issues", number)
            row = item_row(obj, store.get("issues", number, "events", []), start, end, fixes)
            if row is None:
                continue
            kind, last_close = row
            created_day = _day(obj["created_at"])
            created = (created_day - start).days
            items["repo"].append(r)
            items["number"].append(number - last_number)
            items["kind"].append(kind)
            items["created"].append(created - last_created)
            last_number, last_created = number, created
            if last_close is None:
                items["closed"].append(None)
                items["later_in_day"].append(0)
            else:
                days = (_day(last_close) - created_day).days
                items["closed"].append(days)
                exact = _time(last_close) - _time(obj["created_at"])
                items["later_in_day"].append(int(exact > datetime.timedelta(days=days)))
    for what, n in sorted(fixes.items()):
        log(f"fixed up from the item's own state ({what}): {n}")
    return {
        "meta": {"from": start.isoformat(), "to": to.isoformat()},
        "repos": repos,
        "items": items,
    }


def expand(data):
    """The inverse of the layout above, for tests and for reading the file:
    the items with `number` and `created` as values."""
    items = dict(data["items"])
    last = {}
    numbers, created = [], []
    for r, n, c in zip(items["repo"], items["number"], items["created"]):
        ln, lc = last.get(r, (0, 0))
        last[r] = (ln + n, lc + c)
        numbers.append(ln + n)
        created.append(lc + c)
    items["number"], items["created"] = numbers, created
    return items


def write(data, path=None):
    path = Path(path or out_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"
    path.write_text(text, encoding="utf-8")
    return path, len(text.encode())
