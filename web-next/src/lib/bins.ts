// Calendar periods for the bars, and the points the open counts are drawn at.

import { Calendar, MONTHS, dayName, isoWeek } from "./dates.ts";
import type { Bin } from "./state.ts";

export type Period = "day" | "week" | "month" | "quarter";

export interface Bucket {
  /** First and last day in the range (inclusive). */
  start: number;
  end: number;
  /** The range cuts the period short. */
  partial: boolean;
}

/** The first day of the period containing a day. */
function periodStart(cal: Calendar, day: number, period: Period): number {
  const d = cal.date(day);
  switch (period) {
    case "day":
      return day;
    case "week":
      return day - ((d.getUTCDay() + 6) % 7);
    case "month":
      return cal.dayOf(d.getUTCFullYear(), d.getUTCMonth(), 1);
    case "quarter":
      return cal.dayOf(d.getUTCFullYear(), d.getUTCMonth() - (d.getUTCMonth() % 3), 1);
  }
}

function nextStart(cal: Calendar, start: number, period: Period): number {
  const d = cal.date(start);
  switch (period) {
    case "day":
      return start + 1;
    case "week":
      return start + 7;
    case "month":
      return cal.dayOf(d.getUTCFullYear(), d.getUTCMonth() + 1, 1);
    case "quarter":
      return cal.dayOf(d.getUTCFullYear(), d.getUTCMonth() + 3, 1);
  }
}

export function buckets(cal: Calendar, from: number, to: number, period: Period): Bucket[] {
  const out: Bucket[] = [];
  for (let s = periodStart(cal, from, period); s <= to; ) {
    const n = nextStart(cal, s, period);
    const start = Math.max(s, from);
    const end = Math.min(n - 1, to);
    out.push({ start, end, partial: start !== s || end !== n - 1 });
    s = n;
  }
  return out;
}

export const MAX_BARS = 54;

/** "Auto": the smallest of week, month or quarter that gives at most 54 bars. */
export function resolveBin(cal: Calendar, from: number, to: number, bin: Bin): Period {
  if (bin !== "auto") return bin;
  for (const p of ["week", "month"] as const) {
    if (buckets(cal, from, to, p).length <= MAX_BARS) return p;
  }
  return "quarter";
}

export const PERIOD_LABELS: Record<Period, string> = {
  day: "Day",
  week: "Week",
  month: "Month",
  quarter: "Quarter",
};

/** "Mon, Nov 23, 2026", "2026-W48", "November 2026", "2026 Q4" */
export function periodName(cal: Calendar, bucketStart: number, period: Period): string {
  const d = cal.date(bucketStart);
  switch (period) {
    case "day":
      return dayName(d);
    case "week": {
      const { year, week } = isoWeek(d);
      return `${year}-W${String(week).padStart(2, "0")}`;
    }
    case "month":
      return `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
    case "quarter":
      return `${d.getUTCFullYear()} Q${Math.floor(d.getUTCMonth() / 3) + 1}`;
  }
}
