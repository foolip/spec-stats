// PRs merged and issues closed per calendar period (lib/bins.ts), split by
// how long they were open, from creation to the last close (a PR's merge),
// and PRs closed without merging. And PRs or issues opened per period,
// split by how soon they were closed. Each item counts once, at its
// creation or its last close, so the bars agree with the open count.

import type { Data } from "./data.ts";
import type { Period } from "./bins.ts";
import type { Kind } from "./open.ts";

export interface Bands {
  /** Whole days that end each band but the last (Infinity: any time). */
  ends: number[];
  /** One more than `ends`, fastest first. */
  labels: string[];
}

/** Within 1 day, 1–10 days, more than 10 days. For whatwg/html's merges
 * since 2022, timed from ready for review, these split them into near
 * thirds (docs/response-metrics.md). */
export const MERGE_BANDS: Bands = { ends: [1, 10], labels: ["within 1 day", "open 1–10 days", "open >10 days"] };

/** Within 1 week, 1 week to 90 days, more than 90 days. For whatwg/html's
 * issues closed since 2022 these split them into near thirds (39%, 28%
 * and 33%; the median is 15 days). */
export const CLOSE_BANDS: Bands = {
  ends: [7, 90],
  labels: ["within 1 week", "open 1 week–90 days", "open >90 days"],
};

/** Closed within 1 week, closed later, or still open, for items by when
 * they were opened. The same for PRs and issues, so they compare: about
 * 61%, 26% and 13% of PRs opened since 2022, and 24%, 26% and 51% of
 * issues. "Still open" never settles, as old items keep being closed. */
export const OUTCOME_BANDS: Bands = {
  ends: [7, Infinity],
  labels: ["closed within 1 week", "closed later", "still open"],
};

/** Items opened in the window's last this many days may yet be closed
 * within OUTCOME_BANDS' 1 week, so their periods are provisional. */
export const SETTLE_DAYS = 7;

/** What a flow counts: items, each at its last close, banded by their
 * time open, if `bands` is given. */
export interface Flow {
  /** 1 for each item counted. */
  items: Uint8Array;
  bands?: Bands;
}

/** PRs merged in the window, by time to merge. */
export function merges(data: Data): Flow {
  return { items: data.items.merged, bands: MERGE_BANDS };
}

/** PRs closed without merging. */
export function unmergedCloses(data: Data): Flow {
  const { isPr, merged, closed } = data.items;
  return { items: Uint8Array.from(isPr, (p, i) => (p && !merged[i] && closed[i] < Infinity ? 1 : 0)) };
}

/** Issues closed at the end of the window: each at its last close, so an
 * issue closed, reopened and closed again counts once. */
export function closes(data: Data): Flow {
  const { isPr, closed } = data.items;
  return { items: Uint8Array.from(isPr, (p, i) => (!p && closed[i] < Infinity ? 1 : 0)), bands: CLOSE_BANDS };
}

/** Counts per period and band: counts[period][band] (one band, all of
 * them, without `bands`), for the chosen repos. */
export function flowByPeriod(data: Data, flow: Flow, repos: Iterable<number>, ps: Period[]): number[][] {
  const ends = flow.bands?.ends ?? [];
  const counts = ps.map(() => new Array<number>(ends.length + 1).fill(0));
  if (ps.length === 0) return counts;
  const chosen = new Uint8Array(data.repos.name.length);
  for (const r of repos) chosen[r] = 1;
  const lo = ps[0].start;
  const hi = ps[ps.length - 1].end;
  // Each day's period, -1 for none: items come in no particular order.
  const periodOf = new Int32Array(hi - lo + 1).fill(-1);
  ps.forEach((p, j) => periodOf.fill(j, p.start - lo, p.end - lo + 1));
  const { closed, daysOpen, repo } = data.items;
  for (let i = 0; i < closed.length; i++) {
    const d = closed[i];
    if (!flow.items[i] || d < lo || d > hi || !chosen[repo[i]]) continue;
    const j = periodOf[d - lo];
    if (j < 0) continue;
    const band = ends.findIndex((e) => daysOpen[i] <= e);
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
  const { created, isPr, repo, daysOpen } = data.items;
  for (let i = 0; i < created.length; i++) {
    const d = created[i];
    if (d < lo || d > hi || isPr[i] !== pr || !chosen[repo[i]]) continue;
    const j = periodOf[d - lo];
    if (j < 0) continue;
    const band = Number.isNaN(daysOpen[i]) ? -1 : ends.findIndex((e) => daysOpen[i] <= e);
    counts[j][band === -1 ? ends.length : band]++;
  }
  return { counts, periods };
}
