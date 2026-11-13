"""spec-stats command line.

  python3 -m specstats extract [--repo whatwg/dom] [--since 2024-01-01] [--kind pr|issue] [--go]
  python3 -m specstats users [--go]
  python3 -m specstats derive
  python3 -m specstats summarize

Commands that fetch print a plan and do nothing unless given --go
(docs/plan.md, ground rule 1).
"""

import argparse
import sys

from . import derive, extract, github, paths, summarize


def main(argv=None):
    ap = argparse.ArgumentParser(prog="specstats")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ex = sub.add_parser("extract", help="fetch PRs and issues from GitHub (incremental)")
    ex.add_argument("--repo", action="append", help="owner/name; default: config/repos.txt")
    ex.add_argument("--kind", choices=["pr", "issue"], action="append")
    ex.add_argument("--since", help="ISO date: how far back to go (default: whole history)")
    ex.add_argument("--go", action="store_true", help="actually fetch")

    us = sub.add_parser("users", help="fetch public profiles of everyone seen")
    us.add_argument("--go", action="store_true")

    sub.add_parser("derive", help="build derived.sqlite from the raw cache (offline)")
    sub.add_parser("summarize", help="write summaries/ (offline)")

    args = ap.parse_args(argv)

    if args.cmd == "extract":
        repos = args.repo or paths.repos()
        kinds = args.kind or ["pr", "issue"]
        db = extract.connect()
        print(f"Plan: {len(repos)} repos x {kinds}, since {args.since or 'the beginning'}, "
              f"serial, >= {github.MIN_INTERVAL}s between requests.")
        for repo in repos:
            for kind in kinds:
                row = db.execute("SELECT high_water, floor FROM sync WHERE repo=? AND kind=?",
                                 (repo, kind)).fetchone()
                print(f"  {repo} {kind}: " + (f"have {row[1] or 'all'} .. {row[0]}" if row else "nothing yet"))
        if not args.go:
            print("Dry run; pass --go to fetch.")
            return 0
        client = github.Client()
        for repo in repos:
            for kind in kinds:
                extract.extract_repo(client, db, repo, kind, since=args.since)
        print(f"Done: {client.requests} requests.")
    elif args.cmd == "users":
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
