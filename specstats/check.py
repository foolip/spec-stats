"""Consistency checks on the stored data (`check`), offline.

These look for bugs in the end-to-end process (fetching, storing,
committing), not for GitHub being consistent: GitHub's data isn't always
(e.g. whatwg/fullscreen #220, a closed PR with no events at all), so the
extractor stores what it gets and doesn't fail on it. Run after a fetch;
each finding is something to look at, and may turn out to be GitHub's.
"""

from . import extract


def _some(numbers, limit=20):
    return ", ".join(map(str, numbers[:limit])) + (f", … ({len(numbers)} in all)" if len(numbers) > limit else "")


def check_repo(store):
    """[(check, [numbers])] for one repo's files, only the checks that found
    something, or None if nothing's fetched yet. Items updated since
    `from`, or open, should have their details; the rest, only their row.
    Whether every item is stored can't be told offline (`extract
    --reconcile` checks that), but numbers never listed are a note."""
    state = store.state
    if not state.get("items"):
        return None
    idx, gone, refused = store.index(), store.gone(), store.refused()
    found = []

    def add(name, numbers):
        if numbers:
            found.append((name, sorted(numbers)))

    add("stored and also recorded as gone", [n for n in idx if n in gone])
    no_closed, no_merged, no_pull = [], [], []
    row_only = {n for n in idx if not store.full(n)}
    add("stored with details, but closed and last updated before `from` (only the row should be)",
        [n for n in row_only if store.get("issues", n, "events") is not None or store.get("issues", n, "comments")
         is not None or (store.dir / "pulls" / str(n)).exists()])
    for n, info in idx.items():
        if n in row_only:
            continue
        kinds = {e["event"] for e in store.get("issues", n, "events", [])}
        if info["state"] == "closed" and "closed" not in kinds:
            no_closed.append(n)
        if info["merged"] and "merged" not in kinds:
            no_merged.append(n)
        if (info["is_pr"] and store.get("pulls", n) is None
                and "pull" not in refused.get(n, {})):
            no_pull.append(n)
    add("closed with no `closed` event", no_closed)
    add("merged with no `merged` event", no_merged)
    add("a PR with no pulls/{n}/index.json (and no 422 recorded for it)", no_pull)
    add("events stored for a number with no issues/{n}/index.json",
        [n for n, _ in store.lists("issues", "events") if n not in idx])
    return found


def unaccounted(store):
    """Numbers up to the highest stored that are neither stored nor gone,
    once the reconcile has listed every item (`items.rows`): deleted or
    transferred before any listing saw them, or discussions, which share
    the numbers. None before that."""
    if "rows" not in store.state.get("items", {}):
        return None
    idx, gone = store.index(), store.gone()
    return [n for n in range(1, max(idx, default=0) + 1) if n not in idx and n not in gone]


def notes(store):
    """Lines that aren't findings: what GitHub refused (HTTP 422), its
    limits, and numbers never listed (deleted, transferred or discussions)."""
    out = [f"(refused by GitHub, not a finding) #{n} {res}: {message}" for n, r in sorted(store.refused().items())
           for res, message in r.items() if res != "checked_at"]
    missing = unaccounted(store)
    if missing:
        out.append(f"(never listed, not a finding: deleted, transferred or discussions) {_some(missing)}")
    return out


def report(repos=None, root=None):
    """(Markdown report, whether anything was found)."""
    lines, any_found = ["# Consistency checks", ""], False
    for repo in repos or extract.stored_repos(root):
        store = extract.RepoStore(repo, root)
        found = check_repo(store)
        if found is None:
            lines.append(f"- {repo}: nothing fetched yet")
        elif not found:
            lines.append(f"- {repo}: OK")
        else:
            any_found = True
            lines.append(f"- {repo}:")
            lines += [f"  - {name}: {_some(numbers)}" for name, numbers in found]
        lines += [f"  - {line}" for line in notes(store)]
    return "\n".join(lines) + "\n", any_found
