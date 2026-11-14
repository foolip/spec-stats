"""spec-stats command line.

  python3 -m specstats extract [--repo whatwg/dom] [--reconcile] [--max-minutes N] [--dry-run]
  python3 -m specstats stats      offline: what's stored

extract fetches everything that changed since the last run into
data/github/. With --reconcile (weekly), it then checks every issue and PR
number of each repo against GitHub, and exits with an error if the numbers
don't add up.

With --dry-run it only prints the plan and fetches nothing. With
--max-minutes N, no request starts, and no rate-limit pause runs, after N
minutes; the run saves its state and exits normally, and the next run
continues from there.
"""

import argparse
import sys

from . import extract, github, paths


def main(argv=None):
    ap = argparse.ArgumentParser(prog="specstats")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("extract", help="fetch everything changed since the last run")
    p.add_argument("--repo", action="append", help="owner/name; default: config/repos.txt")
    p.add_argument("--reconcile", action="store_true", help="also check every issue and PR number (weekly)")
    p.add_argument("--max-minutes", type=float, help="stop starting requests after this many minutes")
    p.add_argument("--dry-run", action="store_true", help="print the plan, fetch nothing")
    sub.add_parser("stats", help="print what data/github/ holds, as Markdown (offline)")
    args = ap.parse_args(argv)

    if args.cmd == "stats":
        print(stats())
        return 0

    repos = args.repo or paths.repos()
    print(f"Plan: extract {len(repos)} repos{', then reconcile each' if args.reconcile else ''}, serial, "
          f">= {github.MIN_INTERVAL}s between requests. Per-PR resources: {', '.join(extract.load_pr_resources())}.")
    for repo in repos:
        cursors = extract.RepoStore(repo).state.get("cursors", {})
        print(f"  {repo}: " + (", ".join(f"{s} to {c.get('cursor')}" for s, c in cursors.items())
                               if cursors else "nothing yet"))
    if args.dry_run:
        print("Dry run: nothing fetched.")
        return 0
    client = github.Client(seconds_left=args.max_minutes * 60 if args.max_minutes is not None else None)
    failed = []
    for repo in repos:
        store = extract.RepoStore(repo)
        try:
            extract.sync_repo(client, store)
            if args.reconcile:
                r = extract.reconcile(client, store)
                # Every number from 1 to the highest must be stored or gone.
                if r["stored"] + r["gone"] != r["highest"]:
                    failed.append(r)
        except github.DeadlineReached:
            print(f"Stopped at the deadline during {repo}; the next run continues from here.")
            break
    print(f"Done: {client.requests} requests, {client.not_modified} of them unchanged (304).")
    for r in failed:
        print(f"COUNT MISMATCH {r['repo']}: numbers 1..{r['highest']}, but {r['stored']} stored "
              f"and {r['gone']} gone")
    return 1 if failed else 0


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
    lines += ["", "| repo | stream | cursor |", "|---|---|---|"]
    for store in stores:
        for stream, c in store.state.get("cursors", {}).items():
            lines.append(f"| {store.repo} | {stream} | {c.get('cursor')} |")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
