"""Write the small committed summaries the web pages read.

summaries/maintenance.json:
  org_monthly    [month, repo, org, action, count]
  people         trailing 12 complete months: [repo, login, org, action, count]
  concentration  trailing 12 complete months: per repo and action, how many
                 people do 50% and 80% of it, and the top person's share
  response       per repo and quarter: median days to the first response
                 from someone other than the author, for PRs and issues
summaries/org_monthly.csv: the same org_monthly rows, for readable diffs.
"""

import csv
import json
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime, timezone

from . import paths

ACTIONS = ["review", "merge", "comment", "pr", "issue"]
OTHER = "Other"
FOLD_SHARE = 0.005  # orgs with less than this share of all actions fold into Other
ALL = "*"


def month_add(month, n):
    y, m = map(int, month.split("-"))
    m += n
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


def quarter(iso):
    return f"{iso[:4]}-Q{(int(iso[5:7]) - 1) // 3 + 1}"


def people_needed(counts, share):
    """Fewest people whose counts add up to at least `share` of the total."""
    total = sum(counts)
    if not total:
        return 0
    acc = 0
    for i, c in enumerate(sorted(counts, reverse=True), 1):
        acc += c
        if acc >= share * total:
            return i
    return len(counts)


def _days(a, b):
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return (datetime.strptime(b, fmt) - datetime.strptime(a, fmt)).total_seconds() / 86400


def summarize(derived_path=None, out_dir=None, today=None):
    db = sqlite3.connect(derived_path or paths.derived_db())
    out_dir = out_dir or paths.SUMMARIES
    out_dir.mkdir(parents=True, exist_ok=True)
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    current_month = today[:7]

    rows = db.execute(
        "SELECT month, repo, org, action, COUNT(*) FROM actions GROUP BY month, repo, org, action").fetchall()
    org_totals = defaultdict(int)
    for _, _, org, _, n in rows:
        org_totals[org] += n
    grand = sum(org_totals.values()) or 1
    keep = {o for o, n in org_totals.items() if n / grand >= FOLD_SHARE}
    folded = defaultdict(int)
    for month, repo, org, action, n in rows:
        o = org if org in keep else OTHER
        folded[(month, repo, o, action)] += n
    org_monthly = sorted([*k, n] for k, n in folded.items())
    orgs = sorted({r[2] for r in org_monthly}, key=lambda o: (o in (OTHER, "Unknown"), -sum(
        r[4] for r in org_monthly if r[2] == o)))

    # Trailing 12 complete months.
    end = current_month
    start = month_add(end, -12)
    people_rows = db.execute(
        "SELECT repo, login, org, action, COUNT(*) FROM actions WHERE month >= ? AND month < ? "
        "GROUP BY repo, login, org, action", (start, end)).fetchall()
    per = defaultdict(lambda: defaultdict(int))  # (repo, action) -> login -> n
    for repo, login, _, action, n in people_rows:
        per[(repo, action)][login] += n
        per[(ALL, action)][login] += n
    concentration = []
    for (repo, action), by_login in sorted(per.items()):
        counts = list(by_login.values())
        total = sum(counts)
        concentration.append([repo, action, total, len(counts), people_needed(counts, 0.5),
                              people_needed(counts, 0.8), round(max(counts) / total, 3)])

    # First-response time, by quarter the item was opened.
    resp = defaultdict(list)
    open_counts = defaultdict(lambda: [0, 0])  # opened, never answered
    for repo, kind, created, first in db.execute(
            "SELECT repo, kind, created_at, first_response_at FROM items"):
        q = quarter(created)
        for r in (repo, ALL):
            open_counts[(r, kind, q)][0] += 1
            if first:
                resp[(r, kind, q)].append(_days(created, first))
            else:
                open_counts[(r, kind, q)][1] += 1
    response = []
    for key, (opened, unanswered) in sorted(open_counts.items()):
        days = resp.get(key, [])
        response.append([*key, opened, unanswered,
                         round(statistics.median(days), 2) if days else None])

    months = sorted({r[0] for r in org_monthly})
    summary = {
        "generated": today,
        "partial_month": current_month if current_month in months else None,
        "months": months,
        "repos": sorted({r[1] for r in org_monthly}),
        "orgs": orgs,
        "actions": ACTIONS,
        "org_monthly": org_monthly,
        "window": {"from": start, "until": end},
        "people": sorted(map(list, people_rows)),
        "concentration": concentration,
        "response": response,
    }
    (out_dir / "maintenance.json").write_text(json.dumps(summary, separators=(",", ":")) + "\n")
    with open(out_dir / "org_monthly.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month", "repo", "org", "action", "count"])
        w.writerows(org_monthly)
    return summary
