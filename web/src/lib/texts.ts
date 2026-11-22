// What the page shows for a state that needs no data: the dates of the
// range, the bars' period and the controls' labels. One function for the
// prerendered page and the controller, so they always agree
// (docs/site-design.md, "Loading").

import { chooseBin, UNIT, type Bin } from "./bins.ts";
import { dateOf } from "./data.ts";
import { longDate } from "./format.ts";
import { rangeDays, type Context, type Preset, type State, type View } from "./url.ts";

export const BIN_LABELS: Record<Bin, string> = { day: "Day", week: "Week", month: "Month", quarter: "Quarter" };
export const PRESET_LABELS: Record<Preset, string> = { all: "All", "3y": "3 yrs", "1y": "1 yr" };
export const PRESET_TITLES: Record<Preset, string> = { all: "All", "3y": "3 years", "1y": "1 year" };

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
}

export function stateText(state: State, ctx: Context): StateText {
  const [start, end] = rangeDays(state.range, ctx);
  const auto = chooseBin(ctx.from, start, end);
  const bin = state.bin === "auto" ? auto : state.bin;
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
  };
}

export interface ViewText {
  /** The view's name: its heading, its link, and its part of the title. */
  title: string;
  question: string;
  /** What's counted: "PRs", "issues". */
  items: string;
  /** What the bars count, as a verb and a noun: "merged", "merges". */
  done: string;
  doneNoun: string;
}

export const VIEW_TEXT: Record<View, ViewText> = {
  "open-prs": {
    title: "Reviews",
    question: "How many PRs are open, and how many are getting merged?",
    items: "PRs",
    done: "merged",
    doneNoun: "merges",
  },
  "open-issues": {
    title: "Issues",
    question: "How many issues are open, and how many are getting closed?",
    items: "issues",
    done: "closed",
    doneNoun: "closes",
  },
};

/** "HTML · Reviews · spec-stats" */
export function pageTitle(view: View, standard: string | null): string {
  return `${standard ? `${standard} · ` : ""}${VIEW_TEXT[view].title} · spec-stats`;
}

/** "Merged", for a column heading. */
export function capitalized(s: string): string {
  return s[0].toUpperCase() + s.slice(1);
}
