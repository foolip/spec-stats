"""spec-stats command line.

  python3 -m specstats extract [--repo whatwg/dom] [--go]     incremental fetch of everything
  python3 -m specstats reconcile [--repo whatwg/dom] [--go]   weekly: compare every number with GitHub
  python3 -m specstats users [--go]                           public profiles of everyone seen
  python3 -m specstats stats                                  offline: what's stored
  python3 -m specstats derive                                 offline
  python3 -m specstats summarize                              offline

Commands that fetch print a plan and do nothing unless given --go
(docs/plan.md, ground rule 1). Fetched data goes in data/github/.
"""

import argparse
import sys

from . import derive, extract, github, paths, summarize


def main(argv=None):
    ap = argparse.ArgumentParser(prog="specstats")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, help in (("extract", "fetch everything changed since the last run"),
                       ("reconcile", "compare every issue and PR number with GitHub")):
        p = sub.add_parser(name, help=help)
        p.add_argument("--repo", action="append", help="owner/name; default: config/repos.txt")
        p.add_argument("--go", action="store_true", help="actually fetch")
    us = sub.add_parser("users", help="fetch public profiles of everyone seen")
    us.add_argument("--go", action="store_true")
    sub.add_parser("stats", help="print what data/github/ holds, as Markdown (offline)")
    sub.add_parser("derive", help="build derived.sqlite from data/github/ (offline)")
    sub.add_parser("summarize", help="write summaries/ (offline)")
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
        client = github.Client()
        failed = []
        for repo in repos:
            store = extract.RepoStore(repo)
            if args.cmd == "extract":
                extract.sync_repo(client, store)
            else:
                r = extract.reconcile(client, store)
                # Every number from 1 to the highest must be stored or gone.
                if r["stored"] + r["gone"] != r["highest"]:
                    failed.append(r)
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
        extract.extract_users(github.Client(), logins)
    elif args.cmd == "stats":
        print(stats())
    elif args.cmd == "derive":
        print(f"derived {derive.derive()} items into {paths.derived_db()}")
    elif args.cmd == "summarize":
        s = summarize.summarize()
        print(f"wrote {len(s['org_monthly'])} org-month rows, {len(s['months'])} months, to {paths.SUMMARIES}")
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
