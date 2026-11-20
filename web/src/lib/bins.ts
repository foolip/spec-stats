// Calendar periods for binning a range of days: days, ISO weeks, months
// and quarters, clipped to the range (so the first and last may be partial).

import { dateOf, dayOf } from "./data.ts";

export type Bin = "day" | "week" | "month" | "quarter";
export const BINS: readonly Bin[] = ["day", "week", "month", "quarter"];
/** What "auto" chooses from: not days, as a day's merges are mostly 0 to 3. */
const AUTO_BINS: readonly Bin[] = ["week", "month", "quarter"];

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
  if (bin === "day") return date;
  if (bin === "week") d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
  else {
    d.setUTCDate(1);
    if (bin === "quarter") d.setUTCMonth(d.getUTCMonth() - (d.getUTCMonth() % 3));
  }
  return d.toISOString().slice(0, 10);
}

function nextDate(date: string, bin: Bin): string {
  const d = new Date(`${date}T00:00:00Z`);
  if (bin === "day" || bin === "week") d.setUTCDate(d.getUTCDate() + (bin === "day" ? 1 : 7));
  else d.setUTCMonth(d.getUTCMonth() + (bin === "month" ? 1 : 3));
  return d.toISOString().slice(0, 10);
}

/** For "auto": the smallest period, a week or longer, whose bars are at
 * least `minWidth` px wide. */
export function chooseBin(from: string, start: number, end: number, width: number, minWidth = 8): Bin {
  for (const bin of AUTO_BINS) {
    if (width / periods(from, start, end, bin).length >= minWidth) return bin;
  }
  return "quarter";
}

/** "Tue 17 Nov 2026", "2026-W47", "November 2026" or "2026 Q4". */
export function periodName(p: Period, bin: Bin): string {
  const d = new Date(`${p.first}T00:00:00Z`);
  if (bin === "day") {
    return d.toLocaleString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })
      .replace(",", "");
  }
  if (bin === "month") return d.toLocaleString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" });
  if (bin === "quarter") return `${d.getUTCFullYear()} Q${Math.floor(d.getUTCMonth() / 3) + 1}`;
  // ISO week: the week's Thursday decides its year.
  const thu = new Date(d);
  thu.setUTCDate(d.getUTCDate() + 3);
  const jan1 = Date.UTC(thu.getUTCFullYear(), 0, 1);
  const week = Math.floor((thu.getTime() - jan1) / 86_400_000 / 7) + 1;
  return `${thu.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}


/** The days to plot a daily count at so it follows the periods: the
 * range's first day, then each period's last day (clipped to the range).
 * With days, every day. */
export function sampleDays(ps: Period[]): number[] {
  if (ps.length === 0) return [];
  const out = [ps[0].start];
  for (const p of ps) if (p.end !== out[out.length - 1]) out.push(p.end);
  return out;
}
