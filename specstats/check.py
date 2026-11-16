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
    something, or None if nothing's fetched yet. Covers the numbers the
    backfill has reached."""
    state = store.state
    items = state.get("items", {})
    if "highest" not in items:
        return None
    reached = items["next"] - 1 if "next" in items else items["highest"]
    idx, gone, refused = store.index(), store.gone(), store.refused()
    pull_fetched = "pull" in state.get("pr_resources", [])
    found = []

    def add(name, numbers):
        if numbers:
            found.append((name, sorted(numbers)))

    add("neither stored nor gone", [n for n in range(1, reached + 1) if n not in idx and n not in gone])
    add("stored and also recorded as gone", [n for n in idx if n in gone])
    no_closed, no_merged, no_pull = [], [], []
    for n, info in idx.items():
        kinds = {e["event"] for e in store.get("issues", n, "events", [])}
        if info["state"] == "closed" and "closed" not in kinds:
            no_closed.append(n)
        if info["merged"] and "merged" not in kinds:
            no_merged.append(n)
        if (pull_fetched and info["is_pr"] and store.get("pulls", n) is None
                and "pull" not in refused.get(n, {})):
            no_pull.append(n)
    add("closed with no `closed` event", no_closed)
    add("merged with no `merged` event", no_merged)
    add("a PR with no pulls/{n}/index.json (and no 422 recorded for it)", no_pull)
    add("events stored for a number neither stored nor gone",
        [n for n, _ in store.lists("issues", "events") if n <= reached and n not in idx and n not in gone])
    return found


def notes(store):
    """Lines about what GitHub refused (HTTP 422), recorded by the fetch.
    Not findings: GitHub's limits, not bugs in the process."""
    return [f"#{n} {res}: {message}" for n, r in sorted(store.refused().items())
            for res, message in r.items() if res != "checked_at"]


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
        lines += [f"  - (refused by GitHub, not a finding) {line}" for line in notes(store)]
    return "\n".join(lines) + "\n", any_found
