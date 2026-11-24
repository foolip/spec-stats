// Open PRs or issues over time, counted at the end of every day: an item
// is open from its creation (or the window's start) to its last close, as
// GitHub search sees it. Drafts are open PRs.

import { dayOf, type Data } from "./data.ts";

/** Open items at the end of each day of the window. */
export type OpenSeries = Int32Array;

/** Which items are of a kind: PRs or issues. */
export type Kind = "pr" | "issue";

/** Each item's group: 0 for the items of a kind, -1 for the rest. */
export function ofKind(data: Data, kind: Kind): Int32Array {
  const pr = kind === "pr" ? 1 : 0;
  return Int32Array.from(data.items.isPr, (p) => (p === pr ? 0 : -1));
}

/** For each repo index: its open items of a kind, every day. */
export function openByRepo(data: Data, kind: Kind): OpenSeries[] {
  return openByGroup(data, ofKind(data, kind), 1).map((groups) => groups[0]);
}

/** For each repo index and each group (`group[item]`, 0 to groups − 1;
 * items in group -1 are left out): its open items, every day. */
export function openByGroup(data: Data, group: Int32Array, groups: number): OpenSeries[][] {
  // Changes per day, then a running sum: deltas[repo][group][day]. An item
  // closed on a day isn't open at its end.
  const deltas = Array.from({ length: data.repos.name.length }, () =>
    Array.from({ length: groups }, () => new Int32Array(data.days + 1)),
  );
  const { repo, created, closed } = data.items;
  for (let i = 0; i < repo.length; i++) {
    const g = group[i];
    if (g < 0) continue;
    const d = deltas[repo[i]][g];
    d[Math.max(created[i], 0)]++;
    if (closed[i] < data.days) d[closed[i]]--;
  }
  return deltas.map((gs) => gs.map((d) => runningSum(d, data.days)));
}

function runningSum(deltas: Int32Array, days: number): Int32Array {
  const out = new Int32Array(days);
  let n = 0;
  for (let d = 0; d < days; d++) out[d] = n += deltas[d];
  return out;
}

/** The sum of the chosen repos' series. */
export function total(series: OpenSeries[], repos: Iterable<number>, days: number): OpenSeries {
  const out = new Int32Array(days);
  for (const r of repos) for (let d = 0; d < days; d++) out[d] += series[r][d];
  return out;
}

export interface Cohorts {
  /** Labels, oldest first: "older", "2022", …, "2026". */
  labels: string[];
  /** Each item's cohort: an index into labels. */
  of: Int32Array;
}

/** Items grouped by the year they were opened: one group for each of the
 * last `years` calendar years up to the window's end, and one for every item
 * opened before those. A group only shrinks once its year is over. */
export function yearCohorts(data: Data, years = 5): Cohorts {
  const last = Number(data.to.slice(0, 4));
  const first = last - years + 1;
  const labels = ["older"];
  for (let y = first; y <= last; y++) labels.push(String(y));
  // The day each year starts on, compared with each item's day: no date
  // strings per item, which cost about 25 ms on a slow phone.
  const starts = labels.slice(1).map((y) => dayOf(data.from, `${y}-01-01`));
  const { created } = data.items;
  const of = new Int32Array(created.length);
  for (let i = 0; i < of.length; i++) {
    let g = 0;
    while (g < starts.length && created[i] >= starts[g]) g++;
    of[i] = g;
  }
  return { labels, of };
}
