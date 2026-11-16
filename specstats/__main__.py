"""spec-stats command line.

  python3 -m specstats extract [--repo whatwg/html] [--reconcile] [--max-minutes N] [--dry-run]
  python3 -m specstats stats      offline: what's stored
  python3 -m specstats check      offline: consistency checks on what's stored

extract fetches everything that changed since the last run into
data/github/. With --reconcile (weekly), it also re-lists every issue and PR,
to catch deletions and missed updates. It stores what GitHub returns,
consistent or not, and exits with an error (extract.CheckFailed), after
storing what it fetched, only if fetching itself can't be done right.
check looks for inconsistencies in the stored data (bugs in the process,
or GitHub's own) and exits with an error if it finds any.

With --dry-run it only prints the plan and fetches nothing. A run never
waits for rate-limit quota: when the hourly reserve is reached, or GitHub
answers with a rate limit, it stops. With --max-minutes N, no request
starts after N minutes. Either way the run saves its state and exits
normally, and the next run continues from there.
"""

import argparse
import sys

from . import check, extract, github, paths, timeline_check


def main(argv=None):
    ap = argparse.ArgumentParser(prog="specstats")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("extract", help="fetch everything changed since the last run")
    p.add_argument("--repo", action="append", help="owner/name; default: config/repos.txt")
    p.add_argument("--reconcile", action="store_true", help="also check every issue and PR number (weekly)")
    p.add_argument("--max-minutes", type=float, help="stop starting requests after this many minutes")
    p.add_argument("--dry-run", action="store_true", help="print the plan, fetch nothing")
    sub.add_parser("stats", help="print what data/github/ holds, as Markdown (offline)")
    p = sub.add_parser("check", help="consistency checks on data/github/, as Markdown (offline)")
    p.add_argument("--repo", action="append", help="owner/name; default: every stored repo")
    p = sub.add_parser("timeline-check", help="compare the timeline API with the stored lists, "
                       "for a sample of items (fetches only timelines; writes nothing to data/github/)")
    p.add_argument("--repo", default="whatwg/dom", help="a repo with stored data (default: whatwg/dom)")
    p.add_argument("--size", type=int, default=40, help="how many items to sample (default: 40)")
    p.add_argument("numbers", nargs="*", type=int, help="items to check instead of a sample")
    args = ap.parse_args(argv)
    # Show each line as it's printed, even when stdout is a pipe (as in
    # GitHub Actions), where Python would otherwise hold it in a buffer.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    if args.cmd == "stats":
        print(stats())
        return 0
    if args.cmd == "check":
        text, found = check.report(args.repo)
        print(text, end="")
        return 1 if found else 0
    if args.cmd == "timeline-check":
        store = extract.RepoStore(args.repo)
        numbers = args.numbers or timeline_check.sample(store, args.size)
        log = lambda m: print(m, file=sys.stderr)  # the report alone goes to stdout
        print(timeline_check.check(github.Client(log=log), store, numbers, log=log))
        return 0

    repos = args.repo or paths.repos()
    print(f"Plan: extract {len(repos)} repos{', reconciling each' if args.reconcile else ''}, "
          f"one request at a time. Per-PR resources: {', '.join(extract.load_pr_resources())}.")
    for repo in repos:
        print(f"  {repo}: {progress(extract.RepoStore(repo).state)}")
    if args.dry_run:
        print("Dry run: nothing fetched.")
        return 0
    client = github.Client(seconds_left=args.max_minutes * 60 if args.max_minutes is not None else None)
    failed = []
    for repo in repos:
        store = extract.RepoStore(repo)
        try:
            extract.sync_repo(client, store, reconcile_=args.reconcile)
        except extract.CheckFailed as e:
            failed.append(str(e))
        except github.Stopped as e:
            print(f"Stopped during {repo}: {e}. The next run continues from here.")
            break
    print(f"Done: {client.requests} requests.")
    for f in failed:
        print(f"CHECK FAILED: {f}")
    return 1 if failed else 0


def progress(state):
    """Where a repo's fetching is up to, from its state.json."""
    items, events = state.get("items", {}), state.get("events", {})
    if not items:
        return "nothing yet"
    if "next" in items:
        out = f"items backfill at {items['next']} of {items['highest']}"
    else:
        out = f"items up to {items['cursor']} (numbers 1..{items['highest']})"
    if "cursor" in events:
        out += f"; events up to {events['cursor']}"
    return out


def stats(root=None):
    """Counts per repo and the cursors, as Markdown."""
    repos = extract.stored_repos(root)
    if not repos:
        return "Nothing stored yet in data/github/."
    stores = [extract.RepoStore(r, root) for r in repos]
    counts = [s.counts() for s in stores]
    cols = list(counts[0]) if counts else []
    lines = ["| repo | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
    for repo, c in zip(repos, counts):
        lines.append(f"| {repo} | " + " | ".join(f"{c[k]:,}" for k in cols) + " |")
    lines += ["", "| repo | progress |", "|---|---|"]
    for store in stores:
        lines.append(f"| {store.repo} | {progress(store.state)} |")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
