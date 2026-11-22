// PRs merged and issues closed per calendar period (lib/bins.ts), split by
// how long they were open: for a PR, from being ready for review to its
// merge; for an issue, from its creation to its last close. And PRs or
// issues opened per period, split by how soon they were closed.

import type { Data } from "./data.ts";
import type { Period } from "./bins.ts";
import type { Kind } from "./open.ts";

export interface Bands {
  /** Hours that end each band but the last. */
  ends: number[];
  /** One more than `ends`, fastest first. */
  labels: string[];
}

/** Within 1 day, 1–10 days, more than 10 days. For whatwg/html's merges
 * since 2022 these split them into near thirds (docs/response-metrics.md). */
export const MERGE_BANDS: Bands = { ends: [24, 240], labels: ["within 1 day", "open 1–10 days", "open >10 days"] };

/** Within 1 week, 1 week to 90 days, more than 90 days. For whatwg/html's
 * issues closed since 2022 these split them into near thirds (39%, 28%
 * and 33%; the median is 15 days). */
export const CLOSE_BANDS: Bands = {
  ends: [7 * 24, 90 * 24],
  labels: ["within 1 week", "open 1 week–90 days", "open >90 days"],
};

/** Closed within 1 day, in 1–7 days, or not within 7 days (closed later,
 * or still open), for items by when they were opened. */
export const OUTCOME_BANDS: Bands = {
  ends: [24, 7 * 24],
  labels: ["closed within 1 day", "closed in 1–7 days", "open >7 days"],
};

/** Items opened in the window's last this many days may yet be closed
 * within OUTCOME_BANDS' 7 days, so their periods are provisional. */
export const SETTLE_DAYS = 7;

/** What a flow counts: the day of each item's last event of a type, for
 * items with a time open in `hours` (NaN for the rest). */
export interface Flow {
  event: string;
  hours: Float64Array;
  bands: Bands;
}

/** PRs merged in the window: each at its `merged` event. */
export function merges(data: Data): Flow {
  return { event: "merged", hours: data.items.hoursToMerge, bands: MERGE_BANDS };
}

/** Issues closed at the end of the window: each at its last `closed` event,
 * so an issue closed, reopened and closed again counts once. */
export function closes(data: Data): Flow {
  return { event: "closed", hours: data.items.hoursToClose, bands: CLOSE_BANDS };
}

/** Counts per period and band: counts[period][band], for the chosen repos. */
export function flowByPeriod(data: Data, flow: Flow, repos: Iterable<number>, ps: Period[]): number[][] {
  const { ends } = flow.bands;
  const counts = ps.map(() => flow.bands.labels.map(() => 0));
  if (ps.length === 0) return counts;
  const type = data.eventTypes.indexOf(flow.event);
  const chosen = new Uint8Array(data.repos.name.length);
  for (const r of repos) chosen[r] = 1;
  const { day, item, event } = data.events;
  // Each item's last event of the type: an item's events are in time order.
  const last = new Int32Array(data.items.repo.length).fill(-1);
  for (let k = 0; k < day.length; k++) if (event[k] === type) last[item[k]] = day[k];
  const lo = ps[0].start;
  const hi = ps[ps.length - 1].end;
  // Each day's period, -1 for none: items come in no particular order.
  const periodOf = new Int32Array(hi - lo + 1).fill(-1);
  ps.forEach((p, j) => periodOf.fill(j, p.start - lo, p.end - lo + 1));
  for (let i = 0; i < last.length; i++) {
    const d = last[i];
    const h = flow.hours[i];
    if (d < lo || d > hi || Number.isNaN(h) || !chosen[data.items.repo[i]]) continue;
    const j = periodOf[d - lo];
    if (j < 0) continue;
    const band = ends.findIndex((e) => h <= e);
    counts[j][band === -1 ? ends.length : band]++;
  }
  return counts;
}

/** Items of a kind opened per period, by how soon they were closed
 * (OUTCOME_BANDS): counts[period][band], for the chosen repos. An item
 * closed, reopened and closed again counts at its last close, as in
 * `closes`; a PR's merge is its close. Periods ending in the window's last
 * SETTLE_DAYS days are marked provisional. */
export function openedByPeriod(data: Data, kind: Kind, repos: Iterable<number>, ps: Period[]): { counts: number[][]; periods: Period[] } {
  const { ends } = OUTCOME_BANDS;
  const counts = ps.map(() => OUTCOME_BANDS.labels.map(() => 0));
  const periods = ps.map((p) => (p.end >= data.days - SETTLE_DAYS ? { ...p, provisional: true } : p));
  if (ps.length === 0) return { counts, periods };
  const pr = kind === "pr" ? 1 : 0;
  const chosen = new Uint8Array(data.repos.name.length);
  for (const r of repos) chosen[r] = 1;
  const lo = ps[0].start;
  const hi = ps[ps.length - 1].end;
  const periodOf = new Int32Array(hi - lo + 1).fill(-1);
  ps.forEach((p, j) => periodOf.fill(j, p.start - lo, p.end - lo + 1));
  const { created, isPr, repo } = data.items;
  const hours = data.items.hoursToClose;
  for (let i = 0; i < created.length; i++) {
    const d = created[i];
    if (d < lo || d > hi || isPr[i] !== pr || !chosen[repo[i]]) continue;
    const j = periodOf[d - lo];
    if (j < 0) continue;
    const band = Number.isNaN(hours[i]) ? -1 : ends.findIndex((e) => hours[i] <= e);
    counts[j][band === -1 ? ends.length : band]++;
  }
  return { counts, periods };
}
