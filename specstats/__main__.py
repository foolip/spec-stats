"""spec-stats command line.

  python3 -m specstats extract [--repo whatwg/dom] [--go]     incremental fetch of everything
  python3 -m specstats reconcile [--repo whatwg/dom] [--go]   weekly: compare every number with GitHub
  python3 -m specstats users [--go]                           public profiles of everyone seen
  python3 -m specstats derive                                 offline
  python3 -m specstats summarize                              offline

Commands that fetch print a plan and do nothing unless given --go
(docs/plan.md, ground rule 1).
"""

import argparse
import sys

from . import derive, extract, github, paths, summarize

# A reconcile that finds stored and GitHub totals further apart than this
# fails, so a hole in the data is noticed.
COUNT_TOLERANCE = 0


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
    sub.add_parser("derive", help="build derived.sqlite from the raw cache (offline)")
    sub.add_parser("summarize", help="write summaries/ (offline)")
    args = ap.parse_args(argv)

    if args.cmd in ("extract", "reconcile"):
        repos = args.repo or paths.repos()
        db = extract.connect()
        print(f"Plan: {args.cmd} {len(repos)} repos, serial, >= {github.MIN_INTERVAL}s between requests.")
        for repo in repos:
            rows = db.execute("SELECT stream, cursor FROM cursors WHERE repo=?", (repo,)).fetchall()
            print(f"  {repo}: " + (", ".join(f"{s} to {c}" for s, c in rows) if rows else "nothing yet"))
        if not args.go:
            print("Dry run; pass --go to fetch.")
            return 0
        client = github.Client()
        failed = []
        for repo in repos:
            if args.cmd == "extract":
                extract.sync_repo(client, db, repo)
            else:
                r = extract.reconcile(client, db, repo)
                if abs(r["remote_total"] - r["stored"]) > COUNT_TOLERANCE:
                    failed.append(r)
        print(f"Done: {client.requests} requests, {client.not_modified} of them unchanged (304).")
        for r in failed:
            print(f"COUNT MISMATCH {r['repo']}: GitHub has {r['remote_total']}, stored {r['stored']}")
        return 1 if failed else 0
    if args.cmd == "users":
        db = extract.connect()
        logins = extract.users_to_fetch(db)
        print(f"Plan: fetch {len(logins)} profiles, 50 per request.")
        if not args.go:
            print("Dry run; pass --go to fetch.")
            return 0
        extract.extract_users(github.Client(), db, logins)
    elif args.cmd == "derive":
        print(f"derived {derive.derive()} items into {paths.derived_db()}")
    elif args.cmd == "summarize":
        s = summarize.summarize()
        print(f"wrote {len(s['org_monthly'])} org-month rows, {len(s['months'])} months, to {paths.SUMMARIES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
