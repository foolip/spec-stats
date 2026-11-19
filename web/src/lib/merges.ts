// PRs merged per calendar period (ISO week, month or quarter), split by
// how long after being ready for review they were merged.

import { dateOf, dayOf, type Data } from "./data.ts";

export type Bin = "week" | "month" | "quarter";
export const BINS: readonly Bin[] = ["week", "month", "quarter"];

/** Hours to merge that end each band but the last: within 1 day, 1–10 days,
 * more than 10 days. For whatwg/html's merges since 2022 these split them
 * into near thirds (docs/response-metrics.md). */
export const BAND_ENDS = [24, 240];
export const BAND_LABELS = ["within 1 day", "in 1–10 days", "after more than 10 days"];

export interface Period {
  /** First and last day shown, inclusive, from data.from: clipped to the range. */
  start: number;
  end: number;
  /** The whole period's first day (an ISO week's Monday, a month's 1st). */
  first: string;
  /** Whether the range cuts the period short. */
  partial: boolean;
}

/** The calendar periods covering days start..end (inclusive), clipped to them. */
export function periods(from: string, start: number, end: number, bin: Bin): Period[] {
  const out: Period[] = [];
  let first = periodStart(dateOf(from, start), bin);
  while (dayOf(from, first) <= end) {
    const next = periodStart(nextDate(first, bin), bin);
    const a = dayOf(from, first);
    const b = dayOf(from, next) - 1;
    out.push({ start: Math.max(a, start), end: Math.min(b, end), first, partial: a < start || b > end });
    first = next;
  }
  return out;
}

function periodStart(date: string, bin: Bin): string {
  const d = new Date(`${date}T00:00:00Z`);
  if (bin === "week") d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
  else {
    d.setUTCDate(1);
    if (bin === "quarter") d.setUTCMonth(d.getUTCMonth() - (d.getUTCMonth() % 3));
  }
  return d.toISOString().slice(0, 10);
}

function nextDate(date: string, bin: Bin): string {
  const d = new Date(`${date}T00:00:00Z`);
  if (bin === "week") d.setUTCDate(d.getUTCDate() + 7);
  else d.setUTCMonth(d.getUTCMonth() + (bin === "month" ? 1 : 3));
  return d.toISOString().slice(0, 10);
}

/** The smallest period whose bars are at least `minWidth` px wide. */
export function chooseBin(from: string, start: number, end: number, width: number, minWidth = 8): Bin {
  for (const bin of BINS) {
    if (width / periods(from, start, end, bin).length >= minWidth) return bin;
  }
  return "quarter";
}

/** "2026-W47", "November 2026" or "2026 Q4". */
export function periodName(p: Period, bin: Bin): string {
  const d = new Date(`${p.first}T00:00:00Z`);
  if (bin === "month") return d.toLocaleString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" });
  if (bin === "quarter") return `${d.getUTCFullYear()} Q${Math.floor(d.getUTCMonth() / 3) + 1}`;
  // ISO week: the week's Thursday decides its year.
  const thu = new Date(d);
  thu.setUTCDate(d.getUTCDate() + 3);
  const jan1 = Date.UTC(thu.getUTCFullYear(), 0, 1);
  const week = Math.floor((thu.getTime() - jan1) / 86_400_000 / 7) + 1;
  return `${thu.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

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
