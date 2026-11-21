// What the page shows for a state that needs no data: the dates of the
// range, the bars' period and the controls' labels. One function for the
// prerendered page and the controller, so they always agree
// (docs/site-design.md, "Loading").

import { chooseBin, UNIT, type Bin } from "./bins.ts";
import { dateOf } from "./data.ts";
import { longDate } from "./format.ts";
import { fixed, rangeDays, type Context, type Preset, type State } from "./url.ts";

export const BIN_LABELS: Record<Bin, string> = { day: "Day", week: "Week", month: "Month", quarter: "Quarter" };
export const PRESET_LABELS: Record<Preset, string> = { all: "All", "3y": "3 yrs", "1y": "1 yr", "6m": "6 mo", "3m": "3 mo" };
export const PRESET_TITLES: Record<Preset, string> = { all: "All", "3y": "3 years", "1y": "1 year", "6m": "6 months", "3m": "3 months" };

export interface StateText {
  /** First and last day of the range, inclusive, from ctx.from. */
  start: number;
  end: number;
  /** The bars' period: the choice, or what "auto" resolves to. */
  bin: Bin;
  auto: Bin;
  /** "Nov 20, 2025" */
  startDate: string;
  endDate: string;
  /** "ISO week", and "ISO week" as a column heading. */
  unit: string;
  unitTitle: string;
  /** "Auto (week)" */
  autoLabel: string;
  /** "Custom", or the custom range's dates. */
  customLabel: string;
  /** The range's dates, YYYY-MM-DD, for the date inputs. */
  dates: { from: string; to: string };
}

export function stateText(state: State, ctx: Context): StateText {
  const [start, end] = rangeDays(state.range, ctx);
  const auto = chooseBin(ctx.from, start, end);
  const bin = state.bin === "auto" ? auto : state.bin;
  const dates = fixed(state.range, ctx) as { from: string; to: string };
  const unit = UNIT[bin];
  return {
    start,
    end,
    bin,
    auto,
    startDate: longDate(dateOf(ctx.from, start)),
    endDate: longDate(dateOf(ctx.from, end)),
    unit,
    unitTitle: unit[0].toUpperCase() + unit.slice(1),
    autoLabel: `Auto (${BIN_LABELS[auto].toLowerCase()})`,
    customLabel: "from" in state.range ? `${longDate(dates.from)} – ${longDate(dates.to)}` : "Custom",
    dates,
  };
}

/** "HTML · Reviews · spec-stats" */
export function pageTitle(standard: string | null): string {
  return `${standard ? `${standard} · ` : ""}Reviews · spec-stats`;
}
