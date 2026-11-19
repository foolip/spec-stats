// The URL is the view (docs/site-design.md, "The URL is the view"): every
// view, filter and date range is in the query string, defaults left out.
// parse() reads a query string into a whole, valid state, dropping what it
// doesn't understand; serialize() writes the state back.

import { dateOf, dayOf } from "./data.ts";

export const VIEWS = ["open-prs"] as const;
export type View = (typeof VIEWS)[number];

export const PRESETS = ["all", "3y", "1y", "6m", "3m"] as const;
export type Preset = (typeof PRESETS)[number];

export const DRAFTS = ["include", "exclude"] as const;
export type Drafts = (typeof DRAFTS)[number];

export type Range = { preset: Preset } | { from: string; to: string };

export interface State {
  view: View;
  /** One repo's name, or null for every repo. A name, not an index, so
   * links survive repos being added. */
  repo: string | null;
  range: Range;
  drafts: Drafts;
}

const DEFAULT_PRESET: Preset = "1y";

export const DEFAULT: State = {
  view: "open-prs",
  repo: null,
  range: { preset: DEFAULT_PRESET },
  drafts: "include",
};

/** What a query string is checked against. */
export interface Context {
  repoNames: string[];
  /** The window, YYYY-MM-DD. */
  from: string;
  to: string;
}

const DATE = /^\d{4}-\d{2}-\d{2}$/;

function oneOf<T extends string>(values: readonly T[], value: string | null, fallback: T): T {
  return value !== null && (values as readonly string[]).includes(value) ? (value as T) : fallback;
}

function validDate(value: string | null, ctx: Context): string | null {
  if (value === null || !DATE.test(value) || Number.isNaN(Date.parse(value))) return null;
  if (value < ctx.from) return ctx.from;
  if (value > ctx.to) return ctx.to;
  return value;
}

export function parse(search: string, ctx: Context): State {
  const q = new URLSearchParams(search);
  const from = validDate(q.get("from"), ctx);
  const to = validDate(q.get("to"), ctx);
  const range: Range =
    from !== null || to !== null
      ? { from: from ?? ctx.from, to: to ?? ctx.to }
      : { preset: oneOf(PRESETS, q.get("range"), DEFAULT_PRESET) };
  if ("from" in range && range.from > range.to) return parse(withoutRange(q), ctx);
  return {
    view: oneOf(VIEWS, q.get("view"), DEFAULT.view),
    repo: ctx.repoNames.find((n) => n === q.get("repo")) ?? null,
    range,
    drafts: oneOf(DRAFTS, q.get("drafts"), DEFAULT.drafts),
  };
}

function withoutRange(q: URLSearchParams): string {
  const copy = new URLSearchParams(q);
  for (const k of ["from", "to", "range"]) copy.delete(k);
  return copy.toString();
}

/** The query string for a state, "" for the default view. Parameters are
 * in a fixed order, so equal states give equal URLs. */
export function serialize(state: State): string {
  const q = new URLSearchParams();
  if (state.view !== DEFAULT.view) q.set("view", state.view);
  if (state.repo !== null) q.set("repo", state.repo);
  if ("preset" in state.range) {
    if (state.range.preset !== DEFAULT_PRESET) q.set("range", state.range.preset);
  } else {
    q.set("from", state.range.from);
    q.set("to", state.range.to);
  }
  if (state.drafts !== DEFAULT.drafts) q.set("drafts", state.drafts);
  const s = q.toString();
  return s ? `?${s}` : "";
}

/** The repo indexes a state selects. */
export function selectedRepos(repo: string | null, names: string[]): number[] {
  return repo === null ? names.map((_, i) => i) : [names.indexOf(repo)].filter((i) => i >= 0);
}

const PRESET_MONTHS: Record<Exclude<Preset, "all">, number> = { "3y": 36, "1y": 12, "6m": 6, "3m": 3 };

/** The first and last day (inclusive, days from ctx.from) a range covers. */
export function rangeDays(range: Range, ctx: Context): [number, number] {
  const last = dayOf(ctx.from, ctx.to);
  if ("from" in range) return [dayOf(ctx.from, range.from), dayOf(ctx.from, range.to)];
  if (range.preset === "all") return [0, last];
  const end = new Date(`${ctx.to}T00:00:00Z`);
  end.setUTCMonth(end.getUTCMonth() - PRESET_MONTHS[range.preset]);
  end.setUTCDate(end.getUTCDate() + 1);
  return [Math.max(0, dayOf(ctx.from, end.toISOString().slice(0, 10))), last];
}

/** A range with fixed dates, for "link to this view". */
export function fixed(range: Range, ctx: Context): Range {
  const [a, b] = rangeDays(range, ctx);
  return { from: dateOf(ctx.from, a), to: dateOf(ctx.from, b) };
}
