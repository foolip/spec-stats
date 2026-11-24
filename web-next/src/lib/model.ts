// Every figure a view shows, computed from the items in memory.
//
// An item is open at the end of day D if it was created on or before D and
// its last close is after D (docs/site-design.md, "First version").

import { Calendar } from "./dates.ts";
import { ISSUE, PR_MERGED, type Data } from "./data.ts";
import { buckets, periodName, resolveBin, type Period } from "./bins.ts";
import type { State, View } from "./state.ts";

/** Periods ending in the window's last 7 days are provisional for items opened. */
export const SETTLE_DAYS = 7;

export interface Series {
  key: string;
  label: string;
  /** A CSS custom property holding the color. */
  color: string;
}

export interface Bar {
  start: number;
  end: number;
  name: string;
  partial: boolean;
  provisional: boolean;
  values: number[];
  total: number;
}

export interface OpenPoint {
  day: number;
  values: number[];
  total: number;
}

export interface SpecRow {
  name: string;
  standard: string;
  open: number;
  change: number;
  opened: number;
  closed: number;
}

export interface Model {
  view: View;
  spec: string | null;
  from: number;
  to: number;
  end: number;
  period: Period;
  cohorts: Series[];
  /** Open items at the range's first day and the end of each period. */
  openPoints: OpenPoint[];
  /** Open items at the end of every day of the range, by cohort; omitted before the data has loaded. */
  daily?: { values: number[][]; total: number[] };
  openedSeries: Series[];
  opened: Bar[];
  closedSeries: Series[];
  closed: Bar[];
  tiles: { open: number; openBefore: number; change: number; closed: number; opened: number };
  bySpec: SpecRow[];
}

interface ViewDef {
  matches(kind: number): boolean;
  /** Stack order, bottom first. */
  closedSeries: Series[];
  closedBand(kind: number, openDays: number): number;
  /** Counted in the closed/merged tile. */
  tileCounts(kind: number): boolean;
}

const OPENED_SERIES: Series[] = [
  { key: "open", label: "Still open", color: "--age-2" },
  { key: "later", label: "Closed later", color: "--age-1" },
  { key: "week", label: "Closed within 1 week", color: "--age-0" },
];

function openedBand(closedDay: number, openDays: number): number {
  if (closedDay === Infinity) return 0;
  return openDays <= 7 ? 2 : 1;
}

const VIEW_DEFS: Record<View, ViewDef> = {
  issues: {
    matches: (k) => k === ISSUE,
    closedSeries: [
      { key: "slow", label: "More than 90 days", color: "--age-2" },
      { key: "mid", label: "1 week to 90 days", color: "--age-1" },
      { key: "fast", label: "Within 1 week", color: "--age-0" },
    ],
    closedBand: (_k, d) => (d <= 7 ? 2 : d <= 90 ? 1 : 0),
    tileCounts: () => true,
  },
  reviews: {
    matches: (k) => k !== ISSUE,
    closedSeries: [
      { key: "slow", label: "Merged in more than 10 days", color: "--age-2" },
      { key: "mid", label: "Merged in 1–10 days", color: "--age-1" },
      { key: "fast", label: "Merged within 1 day", color: "--age-0" },
      { key: "closed", label: "Closed without merging", color: "--closed" },
    ],
    closedBand: (k, d) => (k !== PR_MERGED ? 3 : d <= 1 ? 2 : d <= 10 ? 1 : 0),
    tileCounts: (k) => k === PR_MERGED,
  },
};

export const COHORT_YEARS = 5;

export function cohortSeries(lastYear: number): Series[] {
  const first = lastYear - COHORT_YEARS + 1;
  const out: Series[] = [{ key: "before", label: `Before ${first}`, color: "--cohort-5" }];
  for (let y = first; y <= lastYear; y++) {
    out.push({ key: String(y), label: String(y), color: `--cohort-${lastYear - y}` });
  }
  return out;
}

export function computeModel(data: Data, state: State, options: { daily?: boolean } = {}): Model {
  const cal = new Calendar(data.from);
  const { items, end } = data;
  const def = VIEW_DEFS[state.view];
  const { from, to } = state;
  const repoIndex = state.spec === null ? -1 : data.repos.findIndex((r) => r.name === state.spec);
  const period = resolveBin(cal, from, to, state.bin);
  const bks = buckets(cal, from, to, period);
  const bucketOf = new Int32Array(to - from + 1);
  bks.forEach((b, i) => bucketOf.fill(i, b.start - from, b.end - from + 1));

  // Cohort layers: before the first of the last five calendar years, then one per year.
  const lastYear = cal.year(end);
  const cohorts = cohortSeries(lastYear);
  const yearStarts: number[] = [];
  for (let y = lastYear - COHORT_YEARS + 1; y <= lastYear; y++) yearStarts.push(cal.dayOf(y, 0, 1));
  const cohortOf = (created: number) => {
    let c = 0;
    while (c < yearStarts.length && created >= yearStarts[c]) c++;
    return c;
  };

  const len = to - from + 1;
  const diff = cohorts.map(() => new Int32Array(len + 1));
  const opened = bks.map(() => new Array(OPENED_SERIES.length).fill(0));
  const closed = bks.map(() => new Array(def.closedSeries.length).fill(0));
  const nRepos = data.repos.length;
  const spec = {
    open: new Int32Array(nRepos),
    before: new Int32Array(nRepos),
    opened: new Int32Array(nRepos),
    closed: new Int32Array(nRepos),
  };

  for (let i = 0; i < items.length; i++) {
    const kind = items.kind[i];
    if (!def.matches(kind)) continue;
    const repo = items.repo[i];
    const created = items.created[i];
    const closedDay = items.closedDay[i];
    const openDays = items.openDays[i];

    // By spec, always for every spec.
    if (created <= to && closedDay > to) spec.open[repo]++;
    if (created <= from - 1 && closedDay > from - 1) spec.before[repo]++;
    if (created >= from && created <= to) spec.opened[repo]++;
    if (closedDay >= from && closedDay <= to && def.tileCounts(kind)) spec.closed[repo]++;

    if (repoIndex >= 0 && repo !== repoIndex) continue;

    const s = Math.max(created, from);
    const e = Math.min(closedDay, to + 1);
    if (s < e) {
      const d = diff[cohortOf(created)];
      d[s - from]++;
      d[e - from]--;
    }
    if (created >= from && created <= to) {
      opened[bucketOf[created - from]][openedBand(closedDay, openDays)]++;
    }
    if (closedDay >= from && closedDay <= to) {
      closed[bucketOf[closedDay - from]][def.closedBand(kind, openDays)]++;
    }
  }

  const values = diff.map((d) => {
    const out = new Array<number>(len);
    let run = 0;
    for (let j = 0; j < len; j++) out[j] = run += d[j];
    return out;
  });
  const total = new Array<number>(len).fill(0);
  for (const v of values) for (let j = 0; j < len; j++) total[j] += v[j];
  const point = (day: number): OpenPoint => ({
    day,
    values: values.map((v) => v[day - from]),
    total: total[day - from],
  });
  const openPoints = [point(from), ...bks.map((b) => point(b.end))];
  // The first day may also be a period's end (with days); draw it once.
  const seen = new Set<number>();
  const points = openPoints.filter((p) => !seen.has(p.day) && seen.add(p.day));

  const bars = (counts: number[][], provisionalAfter: number): Bar[] =>
    bks.map((b, i) => ({
      start: b.start,
      end: b.end,
      name: periodName(cal, b.start, period),
      partial: b.partial,
      provisional: b.end > provisionalAfter,
      values: counts[i],
      total: counts[i].reduce((a, c) => a + c, 0),
    }));

  const sum = (a: Int32Array) => (repoIndex >= 0 ? a[repoIndex] : a.reduce((x, y) => x + y, 0));
  const open = sum(spec.open);
  const openBefore = sum(spec.before);

  return {
    view: state.view,
    spec: repoIndex >= 0 ? state.spec : null,
    from,
    to,
    end,
    period,
    cohorts,
    openPoints: points,
    daily: options.daily ? { values, total } : undefined,
    openedSeries: OPENED_SERIES,
    opened: bars(opened, end - SETTLE_DAYS),
    closedSeries: def.closedSeries,
    closed: bars(closed, Infinity),
    tiles: { open, openBefore, change: open - openBefore, closed: sum(spec.closed), opened: sum(spec.opened) },
    bySpec: data.repos.map((r, i) => ({
      name: r.name,
      standard: r.standard,
      open: spec.open[i],
      change: spec.open[i] - spec.before[i],
      opened: spec.opened[i],
      closed: spec.closed[i],
    })),
  };
}
