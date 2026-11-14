"""spec-stats command line.

  python3 -m specstats extract [--repo whatwg/dom] [--go]     incremental fetch of everything
  python3 -m specstats reconcile [--repo whatwg/dom] [--go]   weekly: compare every number with GitHub
  python3 -m specstats users [--go]                           public profiles of everyone seen
  python3 -m specstats stats                                  offline: what's stored

Commands that fetch print a plan and do nothing unless given --go
(docs/plan.md, ground rule 1). Fetched data goes in data/github/.

They also take --max-minutes N: no request starts, and no rate-limit
pause runs, after that many minutes. The run
then saves its state and exits normally, and the next run continues.
"""

import argparse
import sys

from . import extract, github, paths


def add_deadline_args(p):
    p.add_argument("--max-minutes", type=float, help="stop starting requests after this many minutes")


def seconds_left(args):
    return args.max_minutes * 60 if args.max_minutes is not None else None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="specstats")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, help in (("extract", "fetch everything changed since the last run"),
                       ("reconcile", "compare every issue and PR number with GitHub")):
        p = sub.add_parser(name, help=help)
        p.add_argument("--repo", action="append", help="owner/name; default: config/repos.txt")
        p.add_argument("--go", action="store_true", help="actually fetch")
        add_deadline_args(p)
    us = sub.add_parser("users", help="fetch public profiles of everyone seen")
    us.add_argument("--go", action="store_true")
    add_deadline_args(us)
    sub.add_parser("stats", help="print what data/github/ holds, as Markdown (offline)")
    args = ap.parse_args(argv)

    if args.cmd in ("extract", "reconcile"):
        repos = args.repo or paths.repos()
        print(f"Plan: {args.cmd} {len(repos)} repos, serial, >= {github.MIN_INTERVAL}s between requests."
              + (f" Per-PR resources: {', '.join(extract.load_pr_resources())}." if args.cmd == "extract" else ""))
        for repo in repos:
            cursors = extract.RepoStore(repo).state.get("cursors", {})
            print(f"  {repo}: " + (", ".join(f"{s} to {c.get('cursor')}" for s, c in cursors.items())
                                   if cursors else "nothing yet"))
        if not args.go:
            print("Dry run; pass --go to fetch.")
            return 0
        client = github.Client(seconds_left=seconds_left(args))
        failed = []
        for repo in repos:
            store = extract.RepoStore(repo)
            try:
                if args.cmd == "extract":
                    extract.sync_repo(client, store)
                else:
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
    if args.cmd == "users":
        logins = extract.users_to_fetch()
        print(f"Plan: fetch {len(logins)} profiles, one request each.")
        if not args.go:
            print("Dry run; pass --go to fetch.")
            return 0
        try:
            extract.extract_users(github.Client(seconds_left=seconds_left(args)), logins)
        except github.DeadlineReached:
            print("Stopped at the deadline; the next run fetches the rest.")
    elif args.cmd == "stats":
        print(stats())
    return 0


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
    users = len(list(extract.users_dir(root).glob("*.json")))
    lines += ["", f"Profiles: {users:,}", "", "| repo | stream | cursor |", "|---|---|---|"]
    for store in stores:
        for stream, c in store.state.get("cursors", {}).items():
            lines.append(f"| {store.repo} | {stream} | {c.get('cursor')} |")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
