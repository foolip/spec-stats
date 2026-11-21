"""Build the JSON file the site reads, from data/github/ (offline).

`python3 -m specstats build` writes build/data.json (`docs/site-design.md`):

  {"meta": {"from": "2022-01-01", "to": "2026-11-17"},
   "event_types": ["_carried_in", "_carried_in_as_draft", "_created", "_created_as_draft",
                   "closed", "reopened", "convert_to_draft", "ready_for_review", "merged"],
   "repos":  {"name": ["dom", ...], "standard": ["DOM", ...]},
   "items":  {"repo": [0, ...], "number": [1234, 5, ...], "created": [-412, 3, ...],
              "hours_to_merge": [null, 31, ...], "events": [2, ...]},
   "events": {"day": [0, 17, ...], "event": [0, 4, ...]}}

Each table is stored by column. `items.repo` is an index into `repos`
and `events.event` into `event_types`. Days count UTC days from
`meta.from` (day 0); `created` is the day of the PR's `created_at`,
negative for a PR opened before the window.

The layout is chosen to compress well; the client assumes no order
beyond what decoding needs:
- `items.number` and `items.created` are differences from the previous
  item of the same repo (the first of each repo's items holds its own
  value). Items are written by repo and number, so both are small.
- Events are grouped by item: the first `items.events[0]` events are the
  first item's, the next `items.events[1]` the second's, and so on, each
  item's in time order (a PR reopened and closed on one day has both, in
  that order). `events.day` is the days since the item's previous event,
  or for its first event, since `max(created, 0)`.

This first version holds what open PRs over time needs: PRs only, and
the events that open and close them and make them drafts or ready for
review. One timeline: from `updated_since`
in config/fetch.json to the last full UTC day before the newest
`updated_at` seen in any repo (each repo's `items.cursor`), or the last
reconcile's start (`items.rows`) if newer: every run lists every repo,
so that's when the data was last complete. Nothing before it is published: a PR already
open when it starts gets `_carried_in` on day 0, worked out from its
events before then. `_created` comes from the PR's `created_at`, as
GitHub has no event for it. A merge is a `closed` event too, which is
what ends a PR's open span; `merged` (from the PR's `merged_at`) is there
for counting merges, and doesn't change its state. `items.hours_to_merge`
is the time from the PR being ready for review (created, or its first
`ready_for_review` if it was created as a draft) to its merge, in whole
hours rounded up (merged within that many hours), for PRs merged in the
window, and null for the rest.

Draft status is a second state alongside open or closed, with GitHub's
`convert_to_draft` and `ready_for_review`. GitHub has no event for a PR
created as a draft, so `_created_as_draft` follows `_created` for one
(it was a draft if its first draft event is `ready_for_review`, or, with
none, if it's one now), and `_carried_in_as_draft` marks a PR that was a
draft when the window started, open or not (it may be reopened later;
a PR closed for the whole window is left out).
Only changes of state are published: a `closed` for a PR that's already
closed is left out.

Where a PR's events disagree with its state (closed with no `closed`
event, whatwg/fullscreen #220), the PR's own state wins: a `closed` at
its `closed_at`, or a `reopened` at its `updated_at`; a draft event at
the pull object's `updated_at` where its `draft` differs. `check` keeps
reporting those; the build reports how many it fixed up.
"""

import datetime
import json
from pathlib import Path

from . import extract, paths, sgdb

EVENT_TYPES = ["_carried_in", "_carried_in_as_draft", "_created", "_created_as_draft",
               "closed", "reopened", "convert_to_draft", "ready_for_review", "merged"]
LIFECYCLE = ("closed", "reopened")
DRAFT = ("convert_to_draft", "ready_for_review")


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


def transitions(obj, pull, events, fixes):
    """(time, event type) of the item's changes of open state ("closed",
    "reopened") and draft state ("convert_to_draft", "ready_for_review"),
    in time order, made to agree with the item's (and PR's) own state; and
    whether it was a draft when created."""
    evs = sorted(events, key=lambda e: (e["created_at"], e["id"]))
    out = [(e["created_at"], e["event"]) for e in evs if e["event"] in LIFECYCLE + DRAFT]
    is_open = True
    for _, kind in out:
        if kind in LIFECYCLE:
            is_open = kind == "reopened"
    if is_open != (obj["state"] == "open"):
        if obj["state"] == "closed":
            out.append((obj["closed_at"], "closed"))
            _fix(fixes, "closed with no `closed` event")
        else:
            out.append((obj["updated_at"], "reopened"))
            _fix(fixes, "open after a `closed` event")
    # GitHub has no event for a PR created as a draft: it was one if its
    # first draft event is `ready_for_review`, or, with none, if it's one now.
    first = next((kind for _, kind in out if kind in DRAFT), None)
    if first is not None:
        draft_at_creation = first == "ready_for_review"
    elif pull is None:
        draft_at_creation = False
        _fix(fixes, "no pull object (HTTP 422): taken as never a draft")
    else:
        draft_at_creation = bool(pull.get("draft"))
    draft = draft_at_creation
    for _, kind in out:
        if kind in DRAFT:
            draft = kind == "convert_to_draft"
    if pull is not None and draft != bool(pull.get("draft")):
        out.append((pull["updated_at"], "convert_to_draft" if pull.get("draft") else "ready_for_review"))
        _fix(fixes, "draft state differs from the last draft event")
    out.sort(key=lambda t: t[0])
    return out, draft_at_creation


def item_events(obj, pull, events, start, end, fixes):
    """(day, event type) for one PR within [start, end), `start` and `end`
    as dates: only changes of state, in time order."""
    created = _day(obj["created_at"])
    if created >= end:
        return []
    changes, draft = transitions(obj, pull, events, fixes)
    merged_at = (obj.get("pull_request") or {}).get("merged_at")
    if merged_at:
        changes = sorted(changes + [(merged_at, "merged")], key=lambda t: t[0])
    is_open = True
    out = []

    def carry_in():
        if is_open:
            out.append((start, "_carried_in"))
        if draft:
            out.append((start, "_carried_in_as_draft"))

    if created >= start:
        out.append((created, "_created"))
        if draft:
            out.append((created, "_created_as_draft"))
    carried = created >= start
    for at, kind in changes:
        day = _day(at)
        if day >= end:
            break
        if not carried and day >= start:
            carry_in()
            carried = True
        if kind == "merged":
            if day >= start:
                out.append((day, kind))
            continue
        if kind in LIFECYCLE:
            if is_open == (kind == "reopened"):
                continue  # closed twice, or reopened while open
            is_open = kind == "reopened"
        else:
            if draft == (kind == "convert_to_draft"):
                continue
            draft = kind == "convert_to_draft"
        if day >= start:
            out.append((day, kind))
    if not carried:
        carry_in()
    if all(kind == "_carried_in_as_draft" for _, kind in out):
        return []  # a draft, but closed for the whole window
    return [((d - start).days, kind) for d, kind in out]


def hours_to_merge(obj, pull, events, fixes):
    """Hours from the PR being ready for review to its merge, rounded up:
    from `created_at`, or from its first `ready_for_review` if it was
    created as a draft. Rounded up so that any limit in whole hours ("within
    24 hours") gives the same answer as the exact time."""
    changes, draft_at_creation = transitions(obj, pull, events, {})
    ready = obj["created_at"]
    if draft_at_creation:
        first = next((at for at, kind in changes if kind == "ready_for_review"), None)
        if first is None:
            _fix(fixes, "merged while a draft: hours to merge from `created_at`")
        else:
            ready = first
    taken = _time(obj["pull_request"]["merged_at"]) - _time(ready)
    return max(-(-taken // datetime.timedelta(hours=1)), 0)


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
    items = {"repo": [], "number": [], "created": [], "hours_to_merge": [], "events": []}
    events = {"day": [], "event": []}
    fixes = {}
    for r, (repo, store) in enumerate(stores.items()):
        repos["name"].append(repo.split("/", 1)[1])
        repos["standard"].append(standards[repo])
        index = store.index()
        last_number = last_created = 0  # of the repo's previous item
        for number in sorted(n for n, i in index.items() if i["is_pr"] and store.full(n)):
            obj = store.get("issues", number)
            evs = item_events(obj, store.get("pulls", number), store.get("issues", number, "events", []),
                              start, end, fixes)
            if not evs:
                continue
            created = (_day(obj["created_at"]) - start).days
            items["repo"].append(r)
            items["number"].append(number - last_number)
            items["created"].append(created - last_created)
            last_number, last_created = number, created
            merged = any(kind == "merged" for _, kind in evs)
            items["hours_to_merge"].append(hours_to_merge(obj, store.get("pulls", number),
                                                          store.get("issues", number, "events", []), fixes)
                                           if merged else None)
            items["events"].append(len(evs))
            prev = max(created, 0)
            for day, kind in evs:
                events["day"].append(day - prev)
                events["event"].append(EVENT_TYPES.index(kind))
                prev = day
    for what, n in sorted(fixes.items()):
        log(f"fixed up from the item's own state ({what}): {n}")
    return {
        "meta": {"from": start.isoformat(), "to": to.isoformat()},
        "event_types": EVENT_TYPES,
        "repos": repos,
        "items": items,
        "events": events,
    }


def expand(data):
    """The inverse of the layout above, for tests and for reading the file:
    `items.number` and `items.created` as values, and events as rows of
    (item, day, event type), grouped by item."""
    items = dict(data["items"])
    last = {}
    numbers, created = [], []
    for r, n, c in zip(items["repo"], items["number"], items["created"]):
        ln, lc = last.get(r, (0, 0))
        last[r] = (ln + n, lc + c)
        numbers.append(ln + n)
        created.append(lc + c)
    items["number"], items["created"] = numbers, created
    rows = []
    k = 0
    for i, count in enumerate(items.pop("events")):
        day = max(created[i], 0)
        for _ in range(count):
            day += data["events"]["day"][k]
            rows.append((i, day, data["event_types"][data["events"]["event"][k]]))
            k += 1
    if k != len(data["events"]["day"]):
        raise ValueError(f"items.events adds up to {k}, but there are {len(data['events']['day'])} events")
    return items, rows


def write(data, path=None):
    path = Path(path or out_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"
    path.write_text(text, encoding="utf-8")
    return path, len(text.encode())
