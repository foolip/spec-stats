// Periods' names, with d3-time-format's own en-US names rather than Intl,
// whose first use costs tens of milliseconds on a slow phone
// (docs/site-design.md, "Loading"). Apart from bins.ts, as d3-time-format
// sets up its locale when it's loaded, so the controller, which imports
// bins.ts, would bundle it.

import { utcFormat } from "d3-time-format";
import type { Bin, Period } from "./bins.ts";

/** %G and %V are the ISO week's year and number. */
const FORMATS: Record<Bin, (d: Date) => string> = {
  day: utcFormat("%a, %b %-d, %Y"),
  week: utcFormat("%G-W%V"),
  month: utcFormat("%B %Y"),
  quarter: utcFormat("%Y Q%q"),
};

/** "Tue, Nov 17, 2026", "2026-W47", "November 2026" or "2026 Q4". */
export function periodName(p: Period, bin: Bin): string {
  return FORMATS[bin](new Date(`${p.first}T00:00:00Z`));
}
