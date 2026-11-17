"""Could the items listing's rows be stored instead of GET /issues/{n}? (`listing-check`)

The extractor lists `GET /issues?sort=updated` to find what changed, then
fetches each changed item with `GET /issues/{n}` and stores that. If the
listing's row is the same object, that request could go: one per changed
item, about a quarter of an item's requests.

For a sample (the most and the least recently updated items, so old and
new issues and PRs), this fetches each listed item by number and compares
the two, field by field, nested objects included. An item whose
`updated_at` differs between the two changed in between, and is skipped.
Nothing is written to data/github/.
"""

from collections import Counter

LISTING = {"state": "all", "sort": "updated"}


def diff(listed, item, path=""):
    """[(what, field path)] where the listing's row and the item differ."""
    out = []
    for k in sorted(set(listed) | set(item), key=str):
        p = f"{path}.{k}" if path else str(k)
        if k not in listed:
            out.append(("only in GET /issues/{n}", p))
        elif k not in item:
            out.append(("only in the listing", p))
        elif isinstance(listed[k], dict) and isinstance(item[k], dict):
            out += diff(listed[k], item[k], p)
        elif listed[k] != item[k]:
            out.append(("different values", p))
    return out


def _get(obj, path):
    for k in path.split("."):
        obj = obj.get(k) if isinstance(obj, dict) else None
    return obj


def _short(value, limit=80):
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "…"


def check(client, repo, size=50, log=print):
    """A Markdown report comparing listing rows with GET /issues/{n}."""
    rows = []
    for direction in ("desc", "asc"):
        rows += client.rest(f"/repos/{repo}/issues", dict(LISTING, direction=direction, per_page=size)).data
    seen, sample = set(), []
    for r in rows:  # a small repo lists the same items both ways
        if r["number"] not in seen:
            seen.add(r["number"])
            sample.append(r)
    found, examples, kinds = Counter(), {}, Counter()
    same = skipped = 0
    for i, row in enumerate(sample, 1):
        item = client.rest(f"/repos/{repo}/issues/{row['number']}").data
        if item["updated_at"] != row["updated_at"]:
            skipped += 1
            continue
        kinds["PRs" if "pull_request" in row else "issues"] += 1
        d = diff(row, item)
        same += not d
        for key in d:
            found[key] += 1
            examples.setdefault(key, (row["number"], _get(row, key[1]), _get(item, key[1])))
        if i % 20 == 0:
            log(f"{i} of {len(sample)} compared")
    compared = len(sample) - skipped
    lines = [f"# Listing check: {repo}", "",
             f"{len(sample)} items listed ({size} most and {size} least recently updated), "
             f"{skipped} skipped (changed in between); of the {compared} compared "
             f"({kinds['issues']} issues, {kinds['PRs']} PRs), "
             f"{same} are identical. {client.requests} requests.", ""]
    if found:
        lines += ["| difference | field | items | example |", "|---|---|---|---|"]
        for (what, path), n in sorted(found.items()):
            number, listed, item = examples[(what, path)]
            ex = {"only in the listing": f"#{number}: {_short(listed)}",
                  "only in GET /issues/{n}": f"#{number}: {_short(item)}"}.get(
                what, f"#{number}: listing {_short(listed)}, GET {_short(item)}")
            ex = ex.replace("|", "\\|")
            lines.append(f"| {what} | `{path}` | {n} | {ex} |")
    else:
        lines.append("No differences: the listing's rows are the same objects.")
    return "\n".join(lines) + "\n"
