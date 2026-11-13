# Maintenance load: definitions

The question: **who does the work of keeping the WHATWG Living Standards
going, and how few people carry each one?**

## What counts

`specstats.derive` turns each PR and issue into *actions*, each attributed to
an account and an organization at the time it happened:

| Action | One per | Counted when | Left out |
|---|---|---|---|
| `review` | review submitted on a PR (any state: approved, changes requested, commented, dismissed) | submitted | the PR author's own reviews (replies in review threads show up as reviews by the author) |
| `merge` | merged PR, to whoever merged it (`mergedBy`) | merged | |
| `comment` | conversation comment on an issue or PR | written | comments by the issue or PR author |
| `pr` | merged PR, to its author | merged | unmerged PRs |
| `issue` | issue opened | opened | |

Bots are left out of everything: GraphQL `__typename` `Bot`, logins ending in
`[bot]`, and `config/bots.txt`. Deleted accounts count as `ghost`.

`review`, `merge` and `comment` are the maintenance work. `pr` and `issue`
are the demand on it, so you can compare the two.

## Organizations

In order (`specstats/orgs.py`):

1. `config/affiliations.json`: explicit per-login entries, optionally dated,
   each citing a public source.
2. The `company` field of the account's public GitHub profile, normalized
   through the aliases in `config/companies.json` (`@google`, `Google LLC` →
   Google).
3. Otherwise `Unknown`.

Profiles are fetched once, as they are now, so a dated move between
employers is only right if it's recorded in `affiliations.json`. Orgs with
less than 0.5% of all actions fold into `Other` in the summaries.

## Summaries (`summaries/maintenance.json`)

- `org_monthly`: `[month, repo, org, action, count]`.
- `people`: the trailing 12 complete months, `[repo, login, org, action, count]`.
- `concentration`: the trailing 12 complete months, per repo (and `*` for
  all) and action: `[repo, action, total, people, people_for_50%,
  people_for_80%, top_share]`. "People for 50%" is the fewest people who
  together did half of it, which is roughly the spec's bus factor for that
  kind of work.
- `response`: per repo, kind (`pr` or `issue`) and quarter opened:
  `[repo, kind, quarter, opened, unanswered, median_days_to_first_response]`.
  A response is the first review or comment by anyone other than the author
  or a bot.

`summaries/org_monthly.csv` holds the same `org_monthly` rows, for readable
diffs.

## Known limits

- **Not every kind of maintenance is visible.** Editors also work in Matrix
  chat, in meetings, and through the edits they push to their own PRs. Only
  GitHub reviews, merges and comments are counted.
- **A review isn't weighted by effort.** A one-word approval and a long
  review both count as one; `inline_comments` is stored in `derived.sqlite`
  for a weighted measure later.
- **`company` is free text and often empty.** How big `Unknown` gets is a
  key thing to check after the first fetch. `affiliations.json` is the fix,
  with a public source for each entry.
- **Repos that moved or merged** (the Fullscreen API, specs that became part
  of HTML) only cover their history on GitHub.
