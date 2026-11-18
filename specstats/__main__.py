"""spec-stats command line.

  python3 -m specstats extract [--repo whatwg/html] [--reconcile] [--max-minutes N] [--dry-run]
  python3 -m specstats stats      offline: what's stored
  python3 -m specstats check      offline: consistency checks on what's stored
  python3 -m specstats listing-check [--repo whatwg/dom] [--size 50]
                                  are listing rows the same as GET /issues/{n}?
  python3 -m specstats sync-db    copy whatwg/sg's db.json into config/db.json

extract fetches everything that changed since the last run into
data/github/. Only items (issues and PRs) updated since `updated_since` in
config/fetch.json, or still open, are fetched with their details. With
--reconcile (weekly), it also lists every item, to catch deletions and
missed updates, and stores the listing row of every other item. It stores what GitHub returns,
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

from . import check, extract, github, listing_check, sgdb, timeline_check


def main(argv=None):
    ap = argparse.ArgumentParser(prog="specstats")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("extract", help="fetch everything changed since the last run")
    p.add_argument("--repo", action="append", help="owner/name; default: every standard in config/db.json")
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
    p = sub.add_parser("listing-check", help="compare the items listing's rows with GET /issues/{n}, "
                       "for a sample of items (writes nothing to data/github/)")
    p.add_argument("--repo", default="whatwg/dom", help="owner/name (default: whatwg/dom)")
    p.add_argument("--size", type=int, default=50,
                   help="how many of the most, and of the least, recently updated items (default: 50)")
    sub.add_parser("sync-db", help="copy whatwg/sg's db.json (the Living Standards, whose repos "
                   "are fetched) into config/db.json")
    args = ap.parse_args(argv)
    # Show each line as it's printed, even when stdout is a pipe (as in
    # GitHub Actions), where Python would otherwise hold it in a buffer.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    if args.cmd == "stats":
        print(stats())
        return 0
    if args.cmd == "sync-db":
        sgdb.sync()
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

    if args.cmd == "listing-check":
        log = lambda m: print(m, file=sys.stderr)  # the report alone goes to stdout
        print(listing_check.check(github.Client(log=log), args.repo, args.size, log=log), end="")
        return 0

    repos = args.repo or sgdb.repos()
    print(f"Plan: extract {len(repos)} repos{', reconciling each' if args.reconcile else ''}, "
          f"items updated since {extract.load_updated_since()}, and open ones.")
    for repo in repos:
        print(f"  {repo}: {progress(extract.RepoStore(repo).state)}")
    if args.dry_run:
        print("Dry run: nothing fetched.")
        return 0
    client = github.Client(seconds_left=args.max_minutes * 60 if args.max_minutes is not None else None)
    failed, skipped = [], []
    for repo in repos:
        store = extract.RepoStore(repo)
        try:
            extract.sync_repo(client, store, reconcile_=args.reconcile)
        except extract.CheckFailed as e:
            failed.append(str(e))
        except extract.RepoGone as e:
            print(f"Skipped {e}")
            skipped.append(str(e))
        except github.Stopped as e:
            print(f"Stopped during {repo}: {e}. The next run continues from here.")
            break
    print(f"Done: {client.requests} requests.")
    for s in skipped:
        print(f"SKIPPED (repo not found; not public yet?): {s}")
    for f in failed:
        print(f"CHECK FAILED: {f}")
    return 1 if failed else 0


def progress(state):
    """Where a repo's fetching is up to, from its state.json."""
    items, events = state.get("items", {}), state.get("events", {})
    if not items:
        return "nothing yet"
    if "highest" in items:
        out = "by-number state, converted on the next run"
    elif "started" in items:
        out = f"first listing of items updated since {items['from']}: up to {items.get('cursor', 'the start')}"
    else:
        out = f"items updated since {items['from']}: up to {items['cursor']}"
    if "extend" in items:
        ext = items["extend"]
        out += f"; extending back to {ext['from']}: up to {ext.get('cursor', 'the start')}"
    if not items.get("open", {}).get("done"):
        cursor = items.get("open", {}).get("cursor")
        out += f"; open items listed up to {cursor}" if cursor else "; open items not listed yet"
    out += f"; every item's row as of {items['rows']}" if "rows" in items else "; other rows not listed yet (--reconcile)"
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
