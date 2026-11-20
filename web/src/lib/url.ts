// The URL is the view (docs/site-design.md, "The URL is the view"): the
// view and the spec are in the path, so each has its own prerendered page
// (reviews/, reviews/html/), and the date range and the bars' period are in
// the query string, defaults left out. parse() reads a path and query
// string into a whole, valid state, dropping what it doesn't understand;
// href() writes the state back. Paths are relative to the site's root.

import { BINS, type Bin } from "./bins.ts";
import { dateOf, dayOf } from "./data.ts";

export const VIEWS = ["open-prs"] as const;
export type View = (typeof VIEWS)[number];

/** Each view's directory. */
export const VIEW_PATHS: Record<View, string> = { "open-prs": "reviews" };

export const PRESETS = ["all", "3y", "1y", "6m", "3m"] as const;
export type Preset = (typeof PRESETS)[number];

export type Range = { preset: Preset } | { from: string; to: string };

/** Bars' period: a calendar day, ISO week, month or quarter, or "auto" (the
 * smallest of week, month and quarter that keeps the bars few enough). */
export type BinChoice = Bin | "auto";
export const BIN_CHOICES: readonly BinChoice[] = ["auto", ...BINS];

export interface State {
  view: View;
  /** One repo's name, or null for every repo. A name, not an index, so
   * links survive repos being added. */
  repo: string | null;
  range: Range;
  bin: BinChoice;
}

export const DEFAULT_PRESET: Preset = "1y";

export const DEFAULT: State = {
  view: "open-prs",
  repo: null,
  range: { preset: DEFAULT_PRESET },
  bin: "auto",
};

/** What a URL is checked against. */
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

/** Dates as in GitHub's search, `2024-01-01..2026-11-17`, `*` for an
 * open end; clamped to the window. Null if invalid or backwards. */
function dates(from: string | null, to: string | null, ctx: Context): Range | null {
  const a = validDate(from === "*" ? ctx.from : from, ctx);
  const b = validDate(to === "*" ? ctx.to : to, ctx);
  return a !== null && b !== null && a <= b ? { from: a, to: b } : null;
}

/** `range`: a preset or dates. Null if invalid. */
function parseRange(value: string | null, ctx: Context): Range | null {
  if (value === null) return null;
  if ((PRESETS as readonly string[]).includes(value)) return { preset: value as Preset };
  const m = /^([^.]*)\.\.([^.]*)$/.exec(value);
  return m ? dates(m[1], m[2], ctx) : null;
}

function repoName(value: string | null | undefined, ctx: Context): string | null {
  return ctx.repoNames.find((n) => n === value) ?? null;
}

/**
 * The state for a path relative to the site's root ("", "reviews/",
 * "reviews/html/") and a query string. The site's root is the default
 * view. Two kinds of old links still work, and are rewritten: `?repo=`,
 * before specs had their own pages, and `from` and `to`, which held custom
 * dates until 2026-11-20.
 */
export function parse(path: string, search: string, ctx: Context): State {
  const q = new URLSearchParams(search);
  const [dir, name] = path.split("/");
  const view = VIEWS.find((v) => VIEW_PATHS[v] === dir) ?? DEFAULT.view;
  const legacy = q.has("from") || q.has("to") ? dates(q.get("from") ?? "*", q.get("to") ?? "*", ctx) : null;
  return {
    view,
    repo: repoName(name, ctx) ?? (name ? null : repoName(q.get("repo"), ctx)),
    range: parseRange(q.get("range"), ctx) ?? legacy ?? { preset: DEFAULT_PRESET },
    bin: oneOf(BIN_CHOICES, q.get("bin"), DEFAULT.bin),
  };
}

/** The path for a state, relative to the site's root: its prerendered page. */
export function pagePath(state: Pick<State, "view" | "repo">): string {
  return `${VIEW_PATHS[state.view]}/${state.repo === null ? "" : `${state.repo}/`}`;
}

/** The query string for a state, "" for the defaults. Parameters are in a
 * fixed order, so equal states give equal URLs. */
export function query(state: State): string {
  const q = new URLSearchParams();
  if ("preset" in state.range) {
    if (state.range.preset !== DEFAULT_PRESET) q.set("range", state.range.preset);
  } else {
    q.set("range", `${state.range.from}..${state.range.to}`);
  }
  if (state.bin !== DEFAULT.bin) q.set("bin", state.bin);
  const s = q.toString();
  return s ? `?${s}` : "";
}

/** The whole URL for a state, relative to the site's root. */
export function href(state: State): string {
  return pagePath(state) + query(state);
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
