"""Build the JSON file the site reads, from data/github/ (offline).

`python3 -m specstats build` writes build/data.json (`docs/site-design.md`):

  {"meta": {"from": "2022-01-01", "to": "2026-11-17"},
   "event_types": ["_carried_in", "_created", "closed", "reopened"],
   "repos":  {"name": ["dom", ...], "standard": ["DOM", ...]},
   "items":  {"repo": [0, ...], "number": [1234, ...]},
   "events": {"day": [0, ...], "item": [0, ...], "event": [0, ...]}}

Each table is stored by column. `items.repo` is an index into `repos`,
`events.item` into `items`, `events.event` into `event_types`, and
`events.day` counts UTC days from `meta.from` (day 0). Events are sorted
by day, then item, then time.

This first version holds what open PRs over time needs: PRs only, and
the events that open and close them. One timeline: from `updated_since`
in config/fetch.json to the last full UTC day before every repo's
latest complete listing. Nothing before it is published: a PR already
open when it starts gets `_carried_in` on day 0, worked out from its
events before then. `_created` comes from the PR's `created_at`, as
GitHub has no event for it. A merge is a `closed` event too, so there's
no `merged`. Only changes of state are published: a `closed` for a PR
that's already closed is left out.

Where a PR's events disagree with its state (closed with no `closed`
event, whatwg/fullscreen #220), the PR's own state wins: a `closed` at
its `closed_at`, or a `reopened` at its `updated_at`. `check` keeps
reporting those; the build reports how many it fixed up.
"""

import datetime
import json
from pathlib import Path

from . import extract, paths, sgdb

EVENT_TYPES = ["_carried_in", "_created", "closed", "reopened"]


def out_path():
    return paths.ROOT / "build" / "data.json"


def _day(ts):
    return datetime.date.fromisoformat(ts[:10])


def complete_as_of(store):
    """The day (YYYY-MM-DD) every item updated since `from` was last known to
    be stored: when the latest complete updates listing or reconcile started
    (`items.listed`, a date, or `items.rows`, a time). None while
    the repo's first listing, its listing of old open items, or a listing
    back to a moved start isn't done."""
    s = store.state.get("items", {})
    if "cursor" not in s or "started" in s or "extend" in s or s.get("open") != {"done": True}:
        return None
    times = [t[:10] for t in (s.get("listed"), s.get("rows")) if t]
    return max(times) if times else None


def transitions(obj, events, fixes):
    """(time, "closed" | "reopened") for one item, in order, made to agree
    with the item's own state."""
    out = [(e["created_at"], e["event"]) for e in sorted(events, key=lambda e: (e["created_at"], e["id"]))
           if e["event"] in ("closed", "reopened")]
    state = "open"
    for _, kind in out:
        state = "closed" if kind == "closed" else "open"
    if state != obj["state"]:
        if obj["state"] == "closed":
            out.append((obj["closed_at"], "closed"))
            fixes["closed with no `closed` event"] = fixes.get("closed with no `closed` event", 0) + 1
        else:
            out.append((obj["updated_at"], "reopened"))
            fixes["open after a `closed` event"] = fixes.get("open after a `closed` event", 0) + 1
        out.sort(key=lambda t: t[0])
    return out


def item_events(obj, events, start, end, fixes):
    """(day, event type) for one item within [start, end), only changes of
    state, `start` and `end` as dates."""
    created = _day(obj["created_at"])
    if created >= end:
        return []
    out = []
    state = "open"
    if created >= start:
        out.append((created, "_created"))
    for at, kind in transitions(obj, events, fixes):
        day = _day(at)
        if day >= end:
            break
        new = "closed" if kind == "closed" else "open"
        if new == state:
            continue  # closed twice, or reopened while open
        state = new
        if day >= start:
            out.append((day, kind))
    if created < start:
        # The state at the start is the state before the first published change.
        first_open = (state == "open") if not out else (out[0][1] == "closed")
        if first_open:
            out.insert(0, (start, "_carried_in"))
    return [((d - start).days, kind) for d, kind in out]


def build(root=None, standards=None, updated_since=None, log=print):
    """The site's data, as a dict."""
    standards = standards if standards is not None else sgdb.standards()
    since = updated_since or extract.load_updated_since()
    start = _day(since)
    stores = {}
    for repo in standards:
        store = extract.RepoStore(repo, root)
        if not store.state:
            log(f"{repo}: nothing stored; left out")
        elif store.state.get("items", {}).get("from") != since:
            log(f"{repo}: stored from {store.state.get('items', {}).get('from')}, not {since}; left out")
        elif complete_as_of(store) is None:
            log(f"{repo}: no complete listing yet; left out")
        else:
            stores[repo] = store
    if not stores:
        raise ValueError("no repo has complete data")
    end = min(_day(complete_as_of(s)) for s in stores.values())  # its own day is partial
    to = end - datetime.timedelta(days=1)

    repos = {"name": [], "standard": []}
    items = {"repo": [], "number": []}
    rows = []
    fixes = {}
    for r, (repo, store) in enumerate(stores.items()):
        repos["name"].append(repo.split("/", 1)[1])
        repos["standard"].append(standards[repo])
        index = store.index()
        for number in sorted(n for n, i in index.items() if i["is_pr"] and store.full(n)):
            obj = store.get("issues", number)
            evs = item_events(obj, store.get("issues", number, "events", []), start, end, fixes)
            if not evs:
                continue
            i = len(items["number"])
            items["repo"].append(r)
            items["number"].append(number)
            # In time order within a day too: closed, then reopened, the same day.
            rows.extend((day, i, k, EVENT_TYPES.index(kind)) for k, (day, kind) in enumerate(evs))
    rows.sort()
    for what, n in sorted(fixes.items()):
        log(f"fixed up from the item's own state ({what}): {n}")
    return {
        "meta": {"from": start.isoformat(), "to": to.isoformat()},
        "event_types": EVENT_TYPES,
        "repos": repos,
        "items": items,
        "events": {"day": [r[0] for r in rows], "item": [r[1] for r in rows],
                   "event": [r[3] for r in rows]},
    }


def write(data, path=None):
    path = Path(path or out_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"
    path.write_text(text, encoding="utf-8")
    return path, len(text.encode())
