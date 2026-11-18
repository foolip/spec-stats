// The URL is the view (docs/site-design.md, "The URL is the view"): every
// view, filter and date range is in the query string, defaults left out.
// parse() reads a query string into a whole, valid state, dropping what it
// doesn't understand; serialize() writes the state back.

import { dateOf, dayOf } from "./data.ts";

export const VIEWS = ["open-prs"] as const;
export type View = (typeof VIEWS)[number];

export const PRESETS = ["all", "3y", "1y", "6m", "3m"] as const;
export type Preset = (typeof PRESETS)[number];

export const DRAFTS = ["stack", "exclude"] as const;
export type Drafts = (typeof DRAFTS)[number];

/** Which repos: every one, only some, or every one but some. Names, not
 * indexes, so links survive repos being added. */
export type Repos =
  | { mode: "all" }
  | { mode: "only"; names: string[] }
  | { mode: "except"; names: string[] };

export type Range = { preset: Preset } | { from: string; to: string };

export interface State {
  view: View;
  repos: Repos;
  range: Range;
  drafts: Drafts;
}

export const DEFAULT: State = {
  view: "open-prs",
  repos: { mode: "all" },
  range: { preset: "all" },
  drafts: "stack",
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

function parseRepos(value: string | null, ctx: Context): Repos {
  if (!value) return { mode: "all" };
  const known = new Set(ctx.repoNames);
  const parts = value.split(",").filter(Boolean);
  const except = parts.filter((p) => p.startsWith("-")).map((p) => p.slice(1)).filter((n) => known.has(n));
  const only = parts.filter((p) => !p.startsWith("-")).filter((n) => known.has(n));
  const sorted = (names: string[]) => [...new Set(names)].sort();
  if (only.length) return { mode: "only", names: sorted(only) };
  if (except.length && except.length < known.size) return { mode: "except", names: sorted(except) };
  return { mode: "all" };
}

export function parse(search: string, ctx: Context): State {
  const q = new URLSearchParams(search);
  const from = validDate(q.get("from"), ctx);
  const to = validDate(q.get("to"), ctx);
  const range: Range =
    from !== null || to !== null
      ? { from: from ?? ctx.from, to: to ?? ctx.to }
      : { preset: oneOf(PRESETS, q.get("range"), "all") };
  if ("from" in range && range.from > range.to) return parse(withoutRange(q), ctx);
  return {
    view: oneOf(VIEWS, q.get("view"), DEFAULT.view),
    repos: parseRepos(q.get("repos"), ctx),
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
  if (state.repos.mode === "only") q.set("repos", state.repos.names.join(","));
  if (state.repos.mode === "except") q.set("repos", state.repos.names.map((n) => `-${n}`).join(","));
  if ("preset" in state.range) {
    if (state.range.preset !== "all") q.set("range", state.range.preset);
  } else {
    q.set("from", state.range.from);
    q.set("to", state.range.to);
  }
  if (state.drafts !== DEFAULT.drafts) q.set("drafts", state.drafts);
  // Commas in repo lists stay readable.
  const s = q.toString().replaceAll("%2C", ",");
  return s ? `?${s}` : "";
}

/** The repo indexes a state selects. */
export function selectedRepos(repos: Repos, names: string[]): number[] {
  const all = names.map((_, i) => i);
  if (repos.mode === "only") return all.filter((i) => repos.names.includes(names[i]));
  if (repos.mode === "except") return all.filter((i) => !repos.names.includes(names[i]));
  return all;
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
