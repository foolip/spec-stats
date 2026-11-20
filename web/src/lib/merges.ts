// PRs merged per calendar period (lib/bins.ts), split by how long after
// being ready for review they were merged.

import type { Data } from "./data.ts";
import type { Period } from "./bins.ts";

/** Hours to merge that end each band but the last: within 1 day, 1–10 days,
 * more than 10 days. For whatwg/html's merges since 2022 these split them
 * into near thirds (docs/response-metrics.md). */
export const BAND_ENDS = [24, 240];
export const BAND_LABELS = ["within 1 day", "open 1–10 days", "open >10 days"];

/** Merges per period and band: counts[period][band], for the chosen repos. */
export function mergesByPeriod(data: Data, repos: Iterable<number>, ps: Period[]): number[][] {
  const counts = ps.map(() => BAND_LABELS.map(() => 0));
  if (ps.length === 0) return counts;
  const merged = data.eventTypes.indexOf("merged");
  const chosen = new Uint8Array(data.repos.name.length);
  for (const r of repos) chosen[r] = 1;
  const { day, item, event } = data.events;
  const lo = ps[0].start;
  const hi = ps[ps.length - 1].end;
  let j = 0;
  // Events are sorted by day.
  for (let k = 0; k < day.length; k++) {
    if (event[k] !== merged || day[k] < lo) continue;
    if (day[k] > hi) break;
    const i = item[k];
    if (!chosen[data.items.repo[i]]) continue;
    while (ps[j].end < day[k]) j++;
    const h = data.items.hoursToMerge[i];
    const band = BAND_ENDS.findIndex((e) => h <= e);
    counts[j][band === -1 ? BAND_ENDS.length : band]++;
  }
  return counts;
}
