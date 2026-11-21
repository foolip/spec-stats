# Triage, first response and resolution: research

Research for the dashboards to come (2026-11-19). Nothing in it is built
or decided yet. It covers how other projects define these metrics, what
the stored data supports, measurements under each candidate definition,
and a proposal for the maintainer to decide on (last section).
`docs/site-design.md` ("Metrics", "Durations anchor on their start")
and the decisions log's 2026-11-13 rows from the earlier whatwg/html
prototype are the starting point:

- Response time starts when a PR is ready for review, so a PR opened as
  a draft starts at its first `ready_for_review`.
- "Unanswered" means no response within 7 days.
- The PR author's comments aren't responses, and bots are left out.

All figures below are from `data/github/` as of 2026-11-18. They cover the
items created from 2022-01-01 to 2026-11-17 in all 26 fetched repos:
4,050 issues and 3,485 PRs (2,591 and 1,851 of them in whatwg/html). The
scripts are in the session's scratchpad, not the repo. They're a few
hundred lines of standard-library Python over the JSON files, and take
about 5 seconds to run.

## What others measure

| Source | Metric | Clock | What ends it | Notes |
|---|---|---|---|---|
| CHAOSS, Time to First Response | time to the first response to an activity (issue, PR, email, …) | creation | first response | Filters: the responder's role (e.g. only maintainers), and leaving out bots |
| CHAOSS, Issue Response Time | the same, for issues | creation | first response | Leaves out the author's own replies |
| CHAOSS, Time to Close / Issue Resolution Duration | time an issue or change request stays open | creation | close | Mean or median of closed items |
| CHAOSS, Change Request Review Duration | time from a review being requested to that review | each review request | the review | Per review cycle, not per PR |
| GitHub's `github/issue-metrics` action | time to first response, first review, close, answer; time in draft; time in label | creation; for PRs, draft time excluded | first comment or review by someone other than the author, not a bot | `IGNORE_USERS`; time in label needs `LABELS_TO_MEASURE` |
| Google's code review guide | a response deadline, not a metric: one business day at most | review request | first response | Response, not finished review |
| Hasan et al., MSR 2023 (111,094 PRs, 10 projects) | time to first response | creation | first response | Bots are often first, and many responses in under a minute are bots, so they report first *human* response separately |
| Mozilla (Bugzilla) | "triaged" is a state, not a time | | a component other than Untriaged and a severity set | Triagers go through untriaged bugs weekly or more often |
| Rust (triagebot) | `needs-triage` label added automatically to new issues | | label removed by a triager | Untriaged issues are a label query |
| cosh (Chromium) | no response-time metric | | | Counts review work in the week it was done, not the week a CL landed |

What they all have in common:

- the clock starts at creation (or when the PR is ready for review);
- the responder is anyone other than the author, minus bots, optionally
  only maintainers;
- the summary is a mean or median of the items that got a response or
  were closed.

The last point is the weak spot (below). The ones that measure triage
treat it as a *state* (untriaged, triaged) rather than a duration, and
use a field or label that the WHATWG doesn't have.

## What the data supports, and pitfalls found

**Responses.** A non-author response can be any of these:

- a comment (`issues/{n}/comments.json`);
- a review that isn't `PENDING`, by its `submitted_at`
  (`pulls/{n}/reviews.json`);
- an inline review comment (`pulls/{n}/comments.json`);
- an event by someone else (`events.json`): `labeled`, `assigned`,
  `closed`, `merged`, `review_requested`, `transferred`, ….

All of these have an actor and a time, and they come with every item
that has its details (every item in the window).

**Template labels aren't triage.** 3,024 `labeled` events were applied
within a minute of creation by the item's own author: the issue templates'
labels (`addition/proposal` 529, `needs implementer interest` 480,
`agenda+` 217, …). Only 18 labels in that first minute came from anyone
else. So "first label" means nothing unless the label was added by
someone other than the author, and the WHATWG has no `needs-triage`
label to query.

**`author_association` can't tell who maintains a repo.** On a comment,
review or item it's GitHub's value at fetch time, not when it was written:

- No account has two different values within one repo, across 58,000
  comments written over years, so the value is current, not historical.
- It also depends on whether the account's org membership is visible to
  the token. In whatwg/html, 80 accounts did something on someone else's
  item that needs triage or write access: labeling, assigning, closing,
  merging, requesting review. Of those, 36 show as `MEMBER`, 28 as
  `CONTRIBUTOR` and 14 as `NONE`.
- Conversely, 63 accounts that show as `MEMBER` or `COLLABORATOR` in
  whatwg/html never did any of those things there.

Counting only `MEMBER` and `COLLABORATOR` responses drops real triage
and counts non-maintainers, so the "maintainers only" filter that CHAOSS
suggests can't be built from this field.

**A role can be inferred from permission-gated actions instead.**
Someone who has labeled, assigned, closed or merged *someone else's*
item in a repo has triage access there. The first such action dates when
that access started showing, and the data has it per repo with no extra
fetching. It undercounts people with access who never used it, and
counts people with triage access who aren't editors (W3C i18n staff
adding `i18n-tracker`, for example), whose responses are real responses
anyway. Config, not data, would be needed to do better.
`config/db.json` names the editors, but by name and email, not login.

**Bots barely occur.** The only bot actions are 7 reviews by Copilot
accounts. No comment in the data is by a bot: PR previews edit the PR
body rather than commenting. Bots still need filtering (`type: Bot`,
`[bot]` logins, `Copilot`), but they don't distort WHATWG's figures the
way the MSR 2023 paper found elsewhere. Of the first responses that are
comments, 17 are team pings (`cc @whatwg/canvas`), which route an item
rather than answer it. That's too few to matter.

**Drafts.**

- 262 PRs were created as drafts. 69 of them are still drafts, so they
  have no clock yet.
- 107 drafts had a response before they were ready. That supports
  starting the clock at `ready_for_review`, as the prototype did.

**Authors often resolve their own items first.**

- 206 issues and 320 PRs were closed or merged by their author before
  anyone else responded.
- 253 of 2,579 merged PRs were merged by their author with no approving
  review from anyone else. Most look like editorial changes by an editor.
- Counted as "unanswered", these would look like neglect. They aren't
  waiting for anyone, so the wait should end at the close.

**Editors file issues for themselves.** Issues whose author had already
triaged in the repo get *fewer* quick responses than others: 64% within
7 days, against 75%. Their PRs get a few less: 76%, against 83%. Mixing
the two hides how outside contributors are served, so the opener's role
is a useful split.

**The day of the week.** For issues, the share answered within a day is
63% for those opened on a Tuesday and 40% for a Saturday. A 1-day
threshold mostly measures the weekly cycle; the 7-day one evens it out
(another reason for it beyond the prototype's).

**Censoring is the big one.**

- About half of the issues created since 2022 are still open, so the
  median time to close of the *closed* ones (7.7 days) describes the easy
  half.
- Counting the open ones as "not closed yet" (Kaplan–Meier), the median
  issue takes about 2 years (746 days) to close.
- First responses have the same problem on a smaller scale: 13% of issues
  have none, and their median time to first response goes from 9.7 hours
  (answered items only) to 14.8 hours.
- Any duration metric needs to count items still waiting, as a share
  ("closed within 30 days: 35%") or with a survival estimate.

**Small repos are small.**

- whatwg/html has about 130 new issues and 95 new PRs per 91 days.
- 20 of the other 25 repos have under 5 of each per 91 days, and
  whatwg/testutils under 1. A 91-day rolling median for them is a median
  of 2 or 3 items.
- So per-spec durations need the 364-day window, or counts shown as they
  are ("3 of 4 answered within 7 days").

## Measurements

The tables share these columns:

- *ended*: the share of items whose clock has stopped.
- *KM median*: the Kaplan–Meier median, which counts items still waiting
  as censored. "—" means the share that ended never reached the
  percentile.
- *≤ N d*: the share that ended within N days, over items whose clock
  started at least N days before the window's end.

### First response: which actions count

Issues, all repos:

| A response is | ended | median of ended | KM median | ≤1 d | ≤7 d | ≤30 d |
|---|---|---|---|---|---|---|
| any other person's comment | 77% | 10.5 h | 1.2 d | 49% | 63% | 72% |
| … by `MEMBER` or `COLLABORATOR` only | 64% | 12.5 h | 6.1 d | 39% | 51% | 59% |
| any other person's comment, or label, assignment, close, transfer, … | 87% | 9.7 h | 14.8 h | 56% | 71% | 80% |

PRs, all repos (3,416 with a clock), with reviews and inline review
comments counted as comments:

| A response is | ended | median of ended | KM median | ≤1 d | ≤7 d | ≤30 d |
|---|---|---|---|---|---|---|
| any other person's comment or review | 84% | 9.7 h | 16.0 h | 56% | 74% | 81% |
| … by `MEMBER` or `COLLABORATOR` only | 80% | 12.0 h | 22.9 h | 51% | 69% | 77% |
| … or label, close, merge, review request, … | 88% | 8.7 h | 12.3 h | 61% | 79% | 86% |

The first response, under the widest definition, was:

| | Issues | PRs |
|---|---|---|
| comment | 2,438 | 603 |
| `labeled` | 823 | 143 |
| `closed` | 158 | 64 |
| `assigned` | 84 | 14 |
| review | — | 1,389 |
| inline review comment | — | 701 |
| `review_requested` | — | 51 |
| `merged` | — | 37 |
| none | 485 | 407 |

So for issues, a label from a triager is the first response a fifth of
the time. Leaving events out undercounts triage.

### First response by spec and by year (widest definition)

| | Issues ≤7 d | Issues KM median | PRs ≤7 d | PRs KM median |
|---|---|---|---|---|
| whatwg/html | 73% | 14.2 h | 85% | 11.2 h |
| all but html | 69% | 16.1 h | 73% | 14.9 h |
| 2022 | 72% | 12.6 h | 82% | 11.2 h |
| 2023 | 75% | 11.6 h | 81% | 11.6 h |
| 2024 | 73% | 14.6 h | 81% | 11.0 h |
| 2025 | 75% | 11.3 h | 84% | 10.6 h |
| 2026 (to 2026-11-17) | 59% | 2.9 d | 70% | 19.9 h |

2026 stands out, and it's in the data, not a sign of an incomplete
fetch. 289 issues opened in 2026 got no response within 7 days,
against 204 in 2024 and 214 in 2025:

- 206 of them are in whatwg/html, and 64 were opened in October.
- 116 were opened by someone who had triaged in the repo before.

That's the kind of change the dashboard is for. Why it happened isn't
something these figures say.

### Resolution: issues

| | ended | median of ended | KM median | ≤7 d | ≤30 d | ≤365 d |
|---|---|---|---|---|---|---|
| closed (as of now) | 49% | 7.7 d | 746 d | 24% | 35% | 48% |
| whatwg/html | 50% | 7.4 d | 588 d | 24% | 36% | 49% |
| all but html | 49% | 7.9 d | 969 d | 24% | 33% | 46% |
| opener had triaged in the repo | 53% | 14.0 d | 340 d | 18% | 35% | 50% |
| opener hadn't | 48% | 4.3 d | 1,061 d | 26% | 34% | 47% |

How the 2,003 closed issues were closed:

| `state_reason` | Count | Median days to close |
|---|---|---|
| `completed` | 1,672 | 9.4 |
| `not_planned` | 276 | 1.9 |
| `duplicate` | 55 | 1.0 |

`not_planned` and `duplicate` closes are triage decisions, which are
quick, not fixes. 659 issues were closed by their own author.

84 of 4,050 issues were reopened at least once. Measuring to the first
close rather than the last moves the share closed within 365 days from
48% to 49%, so the choice hardly matters.

### Resolution: PRs (from ready for review)

| | merged | closed unmerged | open | merged ≤7 d | merged ≤30 d | KM median to merge |
|---|---|---|---|---|---|---|
| all | 2,579 | 429 | 408 | 54% | 66% | 4.8 d |
| whatwg/html | 1,287 | 288 | 237 | 45% | 60% | 11.4 d |
| all but html | 1,292 | 141 | 171 | 64% | 73% | 1.7 d |
| opener had triaged in the repo | | | | 63% | 76% | 2.2 d |
| opener hadn't | | | | 43% | 54% | 14.9 d |

Who closed the 458 PRs created since 2022 that were closed without
being merged (this count includes drafts that were never ready):

- 233 were closed by their author;
- 225 by someone else.

A PR either gets merged or gets closed unmerged, so the two outcomes
compete. In the "KM median to merge" column, unmerged closes are treated
as censored, as if they might still be merged, which overstates
merging. The cohort shares ("merged within 30 days") don't have that
problem.

## PR time to merge: which number to track

The question (2026-11-19): what number about PR merge times goes down
in the month editor attention improves, and back up in the month it
lapses, without moving long before or after? And is the median the
most robust choice?

Seven ways of attributing time to merge to a month were compared, on the
data and on a simulation where the true change is known.

| Metric | A month's value |
|---|---|
| **Merge-month median** | median age at merge of the PRs merged that month. The industry convention: DORA's lead time for changes, and cycle time in most PR dashboards |
| **Cohort median** | Kaplan–Meier median time to merge of the PRs that became ready that month |
| **Cohort share** | share of the PRs that became ready that month merged within 30 days |
| **Period median** | median of a synthetic cohort that meets, at every age, the merge rates seen that month (below) |
| **Period share** | the same synthetic cohort's share merged within 30 days, with closes without merging as a competing outcome |
| **Open-age median** | median age of the PRs open and ready at the month's end |
| **Little's law** | mean number of PRs open and ready over the month, divided by merges per day |

**Period** is the life-table method that demographers use for period
life expectancy:

- Age bands are 0–1, 1–2, 2–4, 4–7, 7–14, 14–30, 30–60, 60–90, 90–180,
  180–365 and 365–730 days, and over 730.
- For each band, count the merges in the month of PRs at that age, and
  divide by the PR-days that open, ready PRs spent at that age during
  the month: an occurrence/exposure rate.
- Chain those rates into a survival curve and read off the median or the
  share merged by 30 days. With closes without merging as a competing
  outcome, that share is the Aalen–Johansen cumulative incidence.

Every PR open in the month contributes to that month's value, and only
to it, whenever it was opened. Nothing is revised later.

### Simulation

The simulation runs 48 months:

- About 1 PR a day becomes ready, about whatwg/html's rate.
- 70% are easy (merge rate 1/3 a day) and 30% hard (1/120 a day). A few
  are closed without merging.
- **Step:** merge rates are multiplied by 3 in months 24–29.
- **Sweep:** in month 24 only, every PR older than 60 days is merged, a
  backlog clean-up.

Means of 40 runs:

| Step: merge rates ×3 in months 24–29 | 22 | 23 | **24** | 25 | 29 | **30** | 31 |
|---|---|---|---|---|---|---|---|
| merge-month median (days) | 3.6 | 4.0 | **5.6** | 3.2 | 1.3 | **2.5** | 2.7 |
| cohort median | 4.0 | 3.7 | **1.4** | 1.6 | 1.3 | **4.5** | 3.7 |
| cohort share ≤30 d | 76% | 82% | **87%** | 87% | 82% | **75%** | 80% |
| period median | 4.0 | 4.1 | **1.4** | 1.7 | 1.3 | **4.4** | 4.1 |
| period share ≤30 d | 77% | 77% | **88%** | 87% | 86% | **74%** | 78% |
| open-age median | 76 | 74 | **68** | 46 | 27 | **28** | 40 |
| Little's law | 37 | 39 | **19** | 16 | 13 | **22** | 25 |

| Sweep: PRs over 60 days merged in month 24 | 23 | **24** | 25 | 26 |
|---|---|---|---|---|
| merge-month median (days) | 4.0 | **43.5** | 2.8 | 3.0 |
| cohort and period medians, shares ≤30 d | unchanged | **unchanged** | unchanged | unchanged |
| period mean, capped at 365 days | 35 | **16** | 55 | 52 |
| open-age median | 74 | **20** | 29 | 41 |
| Little's law | 37 | **10** | 21 | 27 |

How each metric behaved:

- **The merge-month median moves the wrong way.**
  - In the month attention improves, editors also merge the old PRs
    waiting for them, so it rises: 4.0 to 5.6 days, and to 43.5 in the
    sweep.
  - Once attention lapses, the PRs still being merged are the quick
    ones, so it looks *better*: 2.5 days in month 30, against about 3.7
    before.
  - The data shows the same in whatwg/html in April 2026. Editors merged
    12 PRs, from 216 that were open and ready, the fewest in 2026, and
    8 of the 12 were under a week old. The merge-month median was
    2.2 days, among the best months, while the period share merged
    within 30 days was 34%, among the worst.
  - It's the conventional metric, and this is its known survivorship
    flaw: it only sees PRs that got merged.
- **The period metrics move in the month and only then.** The period
  median goes 4.1, 1.4, …, 1.3, 4.4, and the period share 77%, 88%, …,
  86%, 74%.
- **The cohort metrics nearly do.** The cohort share moved a month
  early: the cohort of month 23 got 82%, because those PRs were still
  waiting when the change came. That lead grows with the threshold: up
  to 30 days for "within 30 days". A cohort's value is also provisional
  until its PRs have had 30 days, and the median until half of them
  merge. That never happens in some whatwg/html months.
- **The stock-based metrics lag.** The open-age median takes months to
  fall and months to recover. Little's law falls in the month but
  recovers over months, as the backlog builds up again. Both are in
  effect a measure of the backlog, which does change slowly.
- **No median or share at 30 days sees a backlog sweep.** Merging PRs
  older than 60 days doesn't change how a typical PR is treated. A mean
  capped at 365 days sees it, but rebounds after (55 in month 25,
  against 35). The rates at old ages come from few PRs, and the PRs that
  reach those ages depend on the past. Demographers call these selection
  effects; the short-threshold shares showed none. The backlog side is
  better shown by a stock: open PRs waiting more than 30 or 90 days. That
  count drops in the month of a sweep and only grows back as PRs age.

### Is the median robust?

Not here. A median is robust to outliers, but how precise it is depends
on how many items fall near it, and WHATWG's merge times are spread out
almost evenly on a log scale.

PRs ready since 2022, by time to merge:

| | <1 h | 1–6 h | 6–24 h | 1–2 d | 2–4 d | 4–7 d | 7–14 d | 14–30 d | 30–90 d | 90–365 d | >1 y | not merged |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| whatwg/html | 6% | 8% | 11% | 6% | 7% | 7% | 7% | 7% | 6% | 5% | 1% | 29% |
| all but html | 21% | 10% | 14% | 6% | 8% | 5% | 5% | 4% | 4% | 4% | 1% | 20% |

What that means for a median:

- For whatwg/html, about 7% of PRs fall in each doubling of time from
  1 day to 30 days, and the median is about 10 days, in the middle of
  that range.
- In a month of about 30 PRs, the share merged by any given time has a
  sampling error of about √(0.25/30), 9 points. That's more than one
  doubling, so a monthly median can be off by a factor of 2 to 3.
- Where fewer than half the PRs merge, the median is undefined (some
  whatwg/html months).

A share at a fixed threshold has the same 9-point error, but in the unit
it's read in. Measured as roughness (the median month-to-month change,
relative to the series' median), from 2022-04 to 2026-10:

| | html, 30-day window | html, 91-day | all but html, 30-day | all but html, 91-day |
|---|---|---|---|---|
| merge-month median | 62% | 29% | 120% | 21% |
| cohort median | 139% | 25% | 118% | 33% |
| period median | 110% | 31% | 166% | 43% |
| cohort share ≤30 d | 18% | 6% | 12% | 4% |
| period share ≤30 d | 20% | 7% | 18% | 5% |
| period mean ≤365 d | 37% | 12% | 59% | 20% |
| Little's law | 28% | 10% | 30% | 12% |

Shares are 3 to 14 times steadier than medians. Averaged over the
months, the period share matches the cohort share: 60–61% against 60%
for whatwg/html, and 72–74% against 71–72% for the rest. Treating
closes without merging as merely leaving the count, instead of as a
competing outcome, put it 4 to 7 points higher.

### Conventional or proven

- **The conventional software metric** is the median (or mean) time to
  merge, by the month of the merge: DORA's lead time, most cycle-time
  dashboards, and `github/issue-metrics`' time to close. It's widely
  used, but it fails the test above, in both directions.
- **The proven method for this property** is the period life table: age-
  specific occurrence/exposure rates over a calendar period, combined
  into a synthetic cohort, with competing risks where there's more than
  one outcome. National statistics offices publish period life
  expectancy every year for this reason: it reflects that year's
  conditions without waiting for a generation to die out, and isn't
  revised later. It's standard in demography, actuarial work and
  survival analysis (the piecewise-exponential model). It isn't common
  in software dashboards, and I haven't found one that uses it.
- **Little's law** (flow time = work in progress / throughput) is the
  queueing and Kanban convention. It's exact over long periods, but over
  a month it mostly reflects the backlog.

### Old PRs against new

The share merged within N days only uses merge rates at ages under
N days. So it gives no credit for merging a PR older than that, and it
counts against time taken from new PRs to work on old ones. Is that a
problem, or what it should do?

**This kind of target has a known failure.** The NHS in England
measured hospitals by the share of patients treated within 18 weeks.

- That rewarded treating patients who could still make the threshold
  over those who had already missed it.
- A threshold analysis (Quinn et al., BMJ Quality & Safety, 2023) found
  treatments bunched just before 18 weeks, with a drop just after.
- Hospitals met the target with long tails behind it.
- A backstop target for the longest waits (52 weeks) was added. In
  2015, some of the 18-week targets were dropped as perverse
  incentives (BMJ: "simplified").
- An average-wait measure was considered as a replacement, which would
  push the other way, toward the longest waits first.

**Simulation, "divert":** in months 24–29, editors spend their attention
on old PRs. PRs under 30 days old are merged at half the rate, and those
over 60 days at 4 times the rate. Means of 40 runs:

| Month | 23 | 24 | 25 | 29 | 30 | 31 |
|---|---|---|---|---|---|---|
| merges (of which over 90 days old) | 29 (4) | 37 (11) | 33 (5) | 30 (2) | 32 (1) | 28 (2) |
| not merged within 30 days (period) | 23% | 28% | 26% | 27% | 17% | 25% |
| open PRs over 90 days old | 15 | 7 | 4 | 2 | 4 | 7 |
| merges per open PR per month, all ages | 0.84 | 1.18 | 1.22 | 1.25 | 1.35 | 1.07 |
| period mean, capped at 365 days | 36 | 27 | 27 | 30 | 32 | 44 |

- **Only the share counts the diversion against editors:** about 5
  points worse.
- **The backlog count only credits it:** 15 to 2.
- **The all-age merge rate and the capped mean net the two.** They come
  out better here, because 4 times the rate on old PRs outweighs half on
  new ones.
- Month 30's 17% is a transient. The new PRs that waited during the
  diversion include more easy ones, so the rate looks high for a month.

**In the data there's no sign of a trade-off.** Clearing old PRs is a
small part of the work. whatwg/html merges a median of 2 PRs over
90 days old a month, against 19 newer ones. Over 57 months:

- Months with more old-PR merges don't have fewer newer merges: Spearman
  +0.08 for whatwg/html, +0.15 for the rest.
- They don't treat new PRs worse either: +0.19 and −0.11 against the
  share not merged within 30 days.
- None of these is significant: with 57 months, that needs about ±0.26.

So far, attention to old and to new PRs hasn't come at each other's
expense.

**Whether to favor new PRs is a policy choice, not a statistical one.**

For new PRs first:

- the author is still there and the context is fresh;
- a quick merge or review is what keeps contributors coming back;
- the period share already doesn't move when old PRs are cleared.

For old PRs:

- many are normative changes waiting on implementer interest, where
  merging is high-value work;
- a figure that never credits them makes that work invisible;
- once a PR is past N days, the share gives no reason to ever merge it.

Any single number has to pick an exchange rate between the two:

- The share within N days values only PRs under N days old.
- The all-age merge rate weighs every day a PR waits equally. It's
  mostly the size of the old backlog, much of it blocked on others.
- The capped mean weighs every day up to a year equally. It's noisier
  (12% roughness at 91 days for whatwg/html, against 7%) and rebounds
  after changes.

**Proposal:** don't collapse it into one number. Show two figures that
each answer one question, as the NHS ended up doing:

- "Are new PRs handled promptly?": the share not merged within N days.
- "Is the old backlog shrinking?": open PRs waiting more than 90 days,
  or more than a year.

Shown side by side, a diversion looks like what it is: one figure
worse, the other better. If one number is still wanted, the capped mean
is the honest single exchange rate, and the choice of cap should be
recorded in the decisions log.

### Merges per period, by age when merged

A simpler option (2026-11-19): count the PRs merged each week or month,
with each bar split by how long after ready for review they were merged
(within 7 days, 8–90 days, over 90 days), and the number of PRs that
became ready drawn as a line.

- It's a flow, so it's counted in the period the work was done, as cosh
  does, with nothing provisional.
- Old and new work each get a color, so time spent on old PRs shows as
  more dark green, not as a worse number.

whatwg/html since 2022 merges about 22 PRs a month (6 a week; 4 of the
last 52 weeks had none) against about 30 becoming ready:

| Merged | Share of merges |
|---|---|
| within 7 days | 63% |
| 8–90 days | 28% |
| over 90 days | 9% |

**Evenly sized buckets.** For whatwg/html's 1,310 merges since 2022,
the thirds break at 22.8 hours and 8.9 days after ready for review.

| Breaks | Within the first | Between | After the second |
|---|---|---|---|
| 1 day and 10 days | 34% | 34% | 32% |
| 1 day and 7 days | 34% | 29% | 37% |

1 and 10 days is the most even split with round breaks; 1 and 7 days
is easier to explain. The thirds move from year to year: the first
break between 17 hours and 1.3 days, the second between 6.2 and
12.9 days. Four even buckets would break at 12.8 hours, 3.1 days and
16.5 days.

**Presentation (mock-ups, 2026-11-19).** The bars sit under the
open-PRs line, sharing its time axis and date range: two panels, not one
chart with two y-axes. Each bin is the smallest calendar period that
keeps a bar at least 8 px wide at the chart's width (since 2026-11-20,
chosen from the range alone: at most 54 bars, `docs/site-design.md`):

- months for the whole window since 2022 (59 bars, about 12 px each);
- ISO weeks for a year or less (52 bars, about 13 px);
- quarters for anything wider than months allow.

The current period is shaded as partial, and the y-axis says "per
month" or "per week". A smooth 13-week rolling area was tried instead.
It lines up with the daily line just as well, but the split bars read
better when they're wide enough.

**Splitting the open-PRs line (mock-ups, 2026-11-19).** As a stacked
area, the open PRs need a split that doesn't change on its own. Age
bands would: a PR moves up a band just by waiting, so the layers shift
with nothing having happened. Two splits were tried, each reconstructed
for every day since 2022. The end counts match the PRs open now.

- **Review state**, from top to bottom:
  - draft;
  - no response yet;
  - discussed, no verdict;
  - changes requested (the author's move);
  - approved, not merged.

  A verdict is each reviewer's latest approval or change request.
  whatwg/html went from 10 PRs with no response yet on 2022-01-01 to 63
  now, and from 27 approved but not merged to 61. It shows whose move
  each PR is waiting on.
- **Year opened** (a layer cake): opened before 2022, 2022–2023, 2024,
  2025, 2026. A layer only shrinks once its years are over, so clearing
  old PRs shows directly. The 137 PRs open at the start of 2022 are down
  to 70.

- **Age bands that move** (tried at the maintainer's request): under
  1 year on top, then 1–2, 2–3, 3–4 and 4–5 years, and 5 years or more
  at the bottom, recomputed every day.
  - The right edge matches the histogram of open PRs by age.
  - The bottom band grew from 5 PRs to 69 only because PRs passed
    5 years old without being closed, not because anything happened to
    them.
  - Each band's change is PRs aging into it minus PRs aging out or
    closed.

Both use a blue ordinal ramp, so they can't be mixed up with the merge
bars' greens, and drafts are hatched.

**What the bar's height measures.** In the step simulation (merge rates
tripled in months 24–29, about 30 PRs ready a month), merges went from
29 a month to 43 in month 24 and 37 in month 25. By month 27 they were
back to 31, while editors were still three times as fast. When the
speed-up ended they fell to 23, then recovered.

When PRs don't wait long, merges can't exceed the PRs coming in, so the
height mostly measures demand. It shows a *change* in attention as a
one-off pulse while the backlog drains or builds, not its level.

The colors carry the level:

- Merges within 7 days went from 64% to 75% of the total and stayed
  there while the speed-up lasted.
- Merges over 90 days drained to about 1 a month, because few old PRs
  were left.

So the chart reads well as a picture of the work:

- what got merged;
- how old it was;
- against the line, whether merges keep up with PRs becoming ready.

As a single metric of attention it's weaker than the shares above, and
it shouldn't be reduced to "% of merges that were fresh". That's a
merge-month figure, and clearing old PRs pushes it the wrong way, as
with the merge-month median.

### Recommendation

- **Headline:** the period share of PRs merged within N days, at the
  trailing window's merge rates, with closes without merging as a
  competing outcome. Shown as the share *not* merged within N days, it's
  a number that goes down when attention improves.
  - It moved in exactly the simulated months.
  - It's 3 to 14 times steadier than any median.
  - It's defined even when fewer than half the PRs merge, and it's final
    the day the window ends.
  - With the site's default 91-day window, sampling error for
    whatwg/html is roughly ±5 points. A 28-day window responds within
    the month at about ±9 points. Small
    repos need the 364-day window.
- **N:** a threshold near the typical PR's merge time is the most
  sensitive. 7 days (whatwg/html 45%, the rest 64%) or 30 days (60% and
  73%).
- **Companion stock, always shown with it:** open PRs waiting more than
  90 days (or a year), from the open PRs view. It's the one that sees
  backlog clean-ups, and without it the headline rewards ignoring old PRs
  ("Old PRs against new", above).
- **Secondary:** the period median, in the hover or table, with the
  91-day or longer window only.
- **For history:** cohort shares by month or quarter ready, as tables
  ("of the PRs ready in 2024-Q1, 62% were merged within 30 days"),
  marked provisional until the cohort has had N days.
- **Not:** the merge-month median, despite the convention.

Time to merge also depends on more than editors: implementer interest,
tests and authors' revisions all add to it. For editor attention alone,
time to first response (metric 1) or time from a push to the next review
is closer, and the same period method applies to them.

What the browser needs is per PR: when the clock started, when it ended,
and how (merged, closed or open). That's the item attributes already
proposed below. A daily series is a pass over about 3,900 PRs and 12 age
bands per day of the window, which should fit the in-memory design
(`docs/site-design.md`); that's still to be checked in the browser.

The scripts are in the session's scratchpad (`prmerge.py`, `simavg.py`,
`cif.py`, `divert.py`), not the repo.

## Proposal

For the maintainer to decide; the open questions are in the last list.
Each metric goes in the metrics registry (`docs/site-design.md`) with a
version.

### 1. Time to first response (duration; issues and PRs)

- **Clock:** the item's `created_at`. For a PR created as a draft, its
  first `ready_for_review` instead; PRs still in draft have no clock.
- **Response:** the first of these by an account other than the author
  that isn't a bot:
  - a comment;
  - a submitted review;
  - an inline review comment;
  - an event that needs triage or write access: `labeled`, `unlabeled`,
    `assigned`, `milestoned`, `closed`, `merged`, `review_requested`,
    `marked_as_duplicate`, `transferred`, `locked`.

  The author's own template labels are left out by the "other than the
  author" rule.
- **Closed by the author before any response:** the item isn't waiting,
  so it's left out of the denominator (206 issues, 320 PRs), rather than
  counted as unanswered.
- **Shown as** the share answered within 7 days (the headline, as
  decided on 2026-11-13), with the Kaplan–Meier median as a second
  figure. Both are over items whose clock started in the trailing window
  and attributed to that day, and the last 7 days are provisional.
  Median and share answered are what the prototype showed. Kaplan–Meier
  replaces "median of the answered".
- **Split** by issue or PR, by spec (364-day window for all but the
  biggest), and by whether the opener had triaged in the repo before.

### 2. Awaiting first response (stock; the triage metric)

The number of open items whose clock has started and that have had no
response, on each day, by age: under 7 days, 7–30 days, over 30 days.

- It's a backlog that can be driven down, like open PRs, and a page can
  list the items.
- It works for small repos, where a median of three items doesn't.
- The data has 311 such open issues created since 2022, 290 of them
  over 30 days old.
- It's built the same way as the open-PRs stock, from one more
  synthesized event per item, `_first_response` (below).

This is the "untriaged" queue that Mozilla and Rust query for, defined
by activity rather than a field or label the WHATWG doesn't use.

### 3. Time to resolve (duration)

- **Issues:** the share closed within 30 and 365 days of creation, by
  the month or quarter of creation; recent cohorts are provisional.
  - Optionally split `completed` from `not_planned` and `duplicate`
    closes. Those two are triage decisions, so they could join metric 1's
    responses instead.
  - Measure to the last close; reopenings are 2% of issues, so it
    hardly matters.
  - No plain median, since half the issues are open. A Kaplan–Meier
    median only where more than half are resolved, and "over N days"
    otherwise.
- **PRs:** from ready for review, the period share not merged within
  N days, with closes as a competing outcome, as the headline ("PR time
  to merge", above); cohort shares merged, closed unmerged and still open
  7 and 30 days after the clock started, for tables of history.
  - This shows both outcomes without survival estimates that treat
    abandoned PRs as "still might merge".
  - Split by the opener's role: outside contributors' PRs are merged far
    later (median about 15 days against 2).

### What the build would publish

Per item, worked out once at build time (`docs/site-design.md` already
lists "first response" as an item attribute):

- `clock` (day the clock started, or null for drafts);
- `first_response` (day, or null);
- `resolution` (`merged`, `completed`, `not_planned`, `duplicate`,
  `closed`, or null) and its day;
- whether the opener had triaged in the repo before.

For the stock metric, one more synthesized event, `_first_response`.

Durations in days lose the hours. Most first responses take hours, so
the column could be in minutes or hours, if medians in hours are
wanted. With the 7-day threshold as the headline, days may be enough.

### Open questions for the maintainer

1. Do label, assignment and close events by others count as responses
   (proposed), or only comments and reviews (what CHAOSS and
   `github/issue-metrics` count)? The difference is 71% against 63% of
   issues answered within 7 days.
2. Is the inferred role ("had triaged in this repo before") acceptable
   for the opener split, or should editors be listed in config by login?
   (`config/db.json` has editors by name and email only.) Either way,
   only as a split, never per person (ground rule 5).
3. Should responses from anyone count, or only from people with triage
   access? Proposed: anyone. The WHATWG's process welcomes implementers'
   and contributors' answers, and a maintainers-only filter can't be
   built reliably from `author_association`.
4. Hours or days for first-response durations in the published table.
5. Are `not_planned` and `duplicate` closes resolutions (metric 3), or
   triage (metric 1), or both?

## Sources

- CHAOSS metrics: [Time to First Response](https://chaoss.community/kb/metric-time-to-first-response/),
  [Issue Response Time](https://chaoss.community/metric-issue-response-time/),
  [Time to Close](https://chaoss.community/metric-time-to-close/),
  [Issue Resolution Duration](https://chaoss.community/metric-issue-resolution-duration/),
  [Change Requests Duration](https://github.com/chaoss/wg-evolution/blob/main/focus-areas/code-development-efficiency/change-requests-duration.md),
  [draft definition with filters](https://github.com/chaoss/wg-common/blob/2dddd30fe4beefe6d51f261630dbe15e8af75fa1/focus-areas/when/time-to-first-response.md)
  (chaoss.community itself couldn't be reached from this session; the
  definitions are from search summaries and the CHAOSS GitHub repo).
- [github/issue-metrics](https://github.com/github/issue-metrics) README.
- [Google engineering practices: speed of code reviews](https://google.github.io/eng-practices/review/reviewer/speed.html).
- Hasan et al., [Understanding the Time to First Response in GitHub Pull Requests](https://arxiv.org/abs/2304.08426), MSR 2023.
- [Mozilla: Triage for Bugzilla](https://firefox-source-docs.mozilla.org/bug-mgmt/policies/triage-bugzilla.html).
- [Rust Forge: issue triaging](https://forge.rust-lang.org/release/issue-triaging.html).
- [cosh](https://github.com/RByers/cosh) README.
- Quinn et al., [Unintended consequences of the 18-week referral to treatment standard in NHS England: a threshold analysis](https://research.birmingham.ac.uk/en/publications/unintended-consequences-of-the-18-week-referral-to-treatment-stan/), BMJ Quality & Safety, 2023;
  [Nuffield Trust: the growing problem of treatment waiting times](https://www.nuffieldtrust.org.uk/news-item/the-growing-problem-of-treatment-waiting-times);
  [Full Fact: the perverse results of the 18-week wait](https://straightstatistics.fullfact.org/article/perverse-results-18-week-wait);
  [BMJ: hospital treatment targets have been simplified](https://www.bmj.com/content/350/bmj.h3090.full) (2015).
