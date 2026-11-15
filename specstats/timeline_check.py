"""Could the timeline API replace the per-item lists? (`timeline-check`)

For a sample of stored issues and PRs, fetch `GET /issues/{n}/timeline`
and compare it, by id, with what's stored for the same number: issue
comments (`commented`), reviews (`reviewed`), inline review comments
(inside `line-commented`) and issue events (every other event with an id).
For objects found in both, compare their fields. The report says what the
timeline is missing, what only it has, and which of its entries have no id.

Objects created after the stored data was fetched are counted as new, not
as missing. The raw timelines are saved in data/private/timeline/ for a
closer look; nothing is written to data/github/.
"""

import json
import random
from collections import Counter, defaultdict

from . import extract, github, paths

# Stored list -> how the timeline holds the same objects.
KINDS = [
    ("comments", "issues", "comments"),          # `commented` events
    ("reviews", "pulls", "reviews"),             # `reviewed` events
    ("review_comments", "pulls", "comments"),    # `comments` of `line-commented` events
    ("events", "issues", "events"),              # other events with an id
]


def timeline_objects(timeline):
    """{kind: {id: object}} from a timeline, plus a Counter of entries
    without an id, by event type."""
    out = {k: {} for k, _, _ in KINDS}
    no_id = Counter()
    for e in timeline:
        ev = e.get("event")
        if ev == "commented":
            out["comments"][e["id"]] = e
        elif ev == "reviewed":
            out["reviews"][e["id"]] = e
        elif ev == "line-commented":
            no_id[ev] += "id" not in e
            for c in e.get("comments", []):
                out["review_comments"][c["id"]] = c
        elif "id" in e:
            out["events"][e["id"]] = e
        else:
            no_id[ev] += 1
    return out, no_id


def sample(store, size, seed=0):
    """Numbers to check: the items with the most of each kind, then random
    ones, `size` in all."""
    picked = []

    def add(numbers):
        for n in numbers:
            if n not in picked and len(picked) < size:
                picked.append(n)

    per_kind = max(size // 8, 1)
    for _, kind, what in KINDS:
        lists = sorted(store.lists(kind, what), key=lambda x: -len(x[1]))
        add(n for n, _ in lists[:per_kind])
    rest = sorted(store.index())
    random.Random(seed).shuffle(rest)
    add(rest)
    return sorted(picked)


def _fetched_at(store):
    """When the stored data was last fetched, roughly: the newest cursor."""
    s = store.state
    stamps = [v.get("cursor", "") for v in s.get("cursors", {}).values()]
    stamps += [s.get("items", {}).get("cursor", ""), s.get("events", {}).get("cursor", "")]
    return max(stamps)


def _created(obj):
    return obj.get("created_at") or obj.get("submitted_at") or ""


def check(client, store, numbers, log=print):
    """Fetch the timelines and return the Markdown report."""
    out_dir = paths.private_dir() / "timeline" / store.repo
    out_dir.mkdir(parents=True, exist_ok=True)
    fetched_at = _fetched_at(store)
    totals = {k: Counter() for k, _, _ in KINDS}
    missing = {k: [] for k, _, _ in KINDS}          # (number, id, type)
    only_old = {k: [] for k, _, _ in KINDS}
    keys_missing = {k: Counter() for k, _, _ in KINDS}   # stored has the field, timeline doesn't
    keys_extra = {k: Counter() for k, _, _ in KINDS}     # the other way
    values_differ = {k: Counter() for k, _, _ in KINDS}
    stored_types, timeline_types, no_id = Counter(), Counter(), Counter()
    missing_types = defaultdict(Counter)
    requests_before = client.requests
    for n in numbers:
        try:
            timeline = list(extract._all_pages(client, f"/repos/{store.repo}/issues/{n}/timeline"))
        except github.Gone:
            log(f"#{n}: gone")
            continue
        (out_dir / f"{n}.json").write_text(extract.pretty(timeline))
        found, nid = timeline_objects(timeline)
        no_id.update(nid)
        timeline_types.update(e.get("event") for e in timeline)
        for kind, where, what in KINDS:
            stored = {o["id"]: o for o in store.get(where, n, what, []) or []}
            if kind == "events":
                stored_types.update(o["event"] for o in stored.values())
            got = found[kind]
            t = totals[kind]
            t["stored"] += len(stored)
            t["timeline"] += len(got)
            for i, o in stored.items():
                if i not in got:
                    t["missing"] += 1
                    missing[kind].append((n, i, o.get("event") or o.get("state") or ""))
                    if kind == "events":
                        missing_types[o["event"]]["missing"] += 1
                    continue
                t["both"] += 1
                other = got[i]
                keys_missing[kind].update(k for k in o if k not in other)
                keys_extra[kind].update(k for k in other if k not in o)
                values_differ[kind].update(k for k in o if k in other and o[k] != other[k])
            for i, o in got.items():
                if i in stored:
                    continue
                if _created(o) > fetched_at:
                    t["new"] += 1
                else:
                    t["only_timeline"] += 1
                    only_old[kind].append((n, i, o.get("event") or o.get("state") or ""))
        log(f"#{n}: {len(timeline)} timeline entries")
    return report(store.repo, numbers, client.requests - requests_before, fetched_at, totals, missing,
                  only_old, keys_missing, keys_extra, values_differ, stored_types, timeline_types,
                  missing_types, no_id)


def _list(pairs, limit=15):
    shown = ", ".join(f"#{n} {i}" + (f" ({t})" if t else "") for n, i, t in pairs[:limit])
    return shown + (f", … ({len(pairs)} in all)" if len(pairs) > limit else "")


def _keys(counter):
    return ", ".join(f"`{k}` ({c})" for k, c in counter.most_common()) or "none"


def report(repo, numbers, requests, fetched_at, totals, missing, only_old, keys_missing, keys_extra,
           values_differ, stored_types, timeline_types, missing_types, no_id):
    lines = [f"# Timeline check: {repo}", "",
             f"{len(numbers)} items ({requests} requests), compared with data stored up to {fetched_at}.",
             f"Items: {', '.join(map(str, numbers))}", "",
             "| | stored | in timeline | in both | stored, not in timeline | only in timeline (older) "
             "| only in timeline (new) |",
             "|---|---|---|---|---|---|---|"]
    for kind, _, _ in KINDS:
        t = totals[kind]
        lines.append(f"| {kind} | {t['stored']} | {t['timeline']} | {t['both']} | {t['missing']} "
                     f"| {t['only_timeline']} | {t['new']} |")
    lines.append("")
    for kind, _, _ in KINDS:
        lines.append(f"## {kind}")
        lines.append("")
        if missing[kind]:
            lines.append(f"- Stored but not in the timeline: {_list(missing[kind])}")
        if only_old[kind]:
            lines.append(f"- In the timeline but not stored (and not new): {_list(only_old[kind])}")
        lines.append(f"- Fields stored but absent from the timeline's copy: {_keys(keys_missing[kind])}")
        lines.append(f"- Fields only in the timeline's copy: {_keys(keys_extra[kind])}")
        lines.append(f"- Fields whose values differ: {_keys(values_differ[kind])}")
        lines.append("")
    lines.append("## Event types")
    lines.append("")
    lines.append("| event | stored (events) | timeline entries | stored, not in timeline |")
    lines.append("|---|---|---|---|")
    for ev in sorted(set(stored_types) | set(timeline_types), key=str):
        lines.append(f"| {ev} | {stored_types[ev]} | {timeline_types[ev]} | {missing_types[ev]['missing']} |")
    lines.append("")
    lines.append(f"Timeline entries without an id: {_keys(no_id)}")
    return "\n".join(lines) + "\n"
