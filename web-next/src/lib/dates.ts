// Days are UTC days counted from the window's first day (`meta.from`), day 0.
// Dates are formatted by hand in en-US, so nothing depends on Intl's locale data.

const DAY_MS = 86_400_000;

export const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** Milliseconds since the epoch of an ISO date (YYYY-MM-DD) at 00:00 UTC, or NaN. */
export function parseIsoDate(text: string): number {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
  if (!m) return NaN;
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const t = Date.UTC(y, mo - 1, d);
  const date = new Date(t);
  // Reject dates that roll over, such as 2026-02-30.
  if (date.getUTCFullYear() !== y || date.getUTCMonth() !== mo - 1 || date.getUTCDate() !== d) return NaN;
  return t;
}

export function isoDate(t: number): string {
  return new Date(t).toISOString().slice(0, 10);
}

/** A calendar for one window: converts between day indexes and dates. */
export class Calendar {
  readonly origin: number;
  constructor(from: string) {
    this.origin = parseIsoDate(from);
    if (Number.isNaN(this.origin)) throw new Error(`bad date: ${from}`);
  }
  time(day: number): number {
    return this.origin + day * DAY_MS;
  }
  date(day: number): Date {
    return new Date(this.time(day));
  }
  iso(day: number): string {
    return isoDate(this.time(day));
  }
  /** The day index of an ISO date, or NaN if it isn't one. */
  day(iso: string): number {
    const t = parseIsoDate(iso);
    return Number.isNaN(t) ? NaN : Math.round((t - this.origin) / DAY_MS);
  }
  /** The day index of 00:00 UTC on a calendar date (month 0-based; it may overflow). */
  dayOf(year: number, month: number, date: number): number {
    return Math.round((Date.UTC(year, month, date) - this.origin) / DAY_MS);
  }
  year(day: number): number {
    return this.date(day).getUTCFullYear();
  }
}

/** "Nov 23, 2026" */
export function mediumDate(d: Date): string {
  return `${MONTHS[d.getUTCMonth()].slice(0, 3)} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
}

/** "Mon, Nov 23, 2026" */
export function dayName(d: Date): string {
  return `${WEEKDAYS[d.getUTCDay()]}, ${mediumDate(d)}`;
}

/** "23 November 2026", as the standards write their Last Updated date. */
export function standardDate(d: Date): string {
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

/** The ISO 8601 week-numbering year and week of a date. */
export function isoWeek(d: Date): { year: number; week: number } {
  const t = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  const weekday = (t.getUTCDay() + 6) % 7; // Monday 0
  t.setUTCDate(t.getUTCDate() - weekday + 3); // the week's Thursday
  const year = t.getUTCFullYear();
  const week = 1 + Math.floor((t.getTime() - Date.UTC(year, 0, 1)) / DAY_MS / 7);
  return { year, week };
}

/** "1,234" */
export function formatCount(n: number): string {
  const sign = n < 0 ? "−" : "";
  const s = String(Math.abs(Math.round(n)));
  return sign + s.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/** "+12", "−3", "0" */
export function formatChange(n: number): string {
  return n > 0 ? `+${formatCount(n)}` : formatCount(n);
}

export function formatPercent(part: number, whole: number): string {
  if (!whole) return "–";
  return `${Math.round((100 * part) / whole)}%`;
}
