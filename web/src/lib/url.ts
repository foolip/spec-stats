// The URL is the view (docs/site-design.md, "The URL is the view"): the
// view and the spec are in the path, so each has its own prerendered page
// (reviews/, reviews/html/, issues/html/), and the date range (`from` and
// `to`, as on GitHub's contributors graph) and the bars' period are in the
// query string, defaults left out. parse() reads a path and query
// string into a whole, valid state, dropping what it doesn't understand;
// href() writes the state back. Paths are relative to the site's root.

import { BINS, type Bin } from "./bins.ts";
import { dateOf, dayOf } from "./data.ts";

/** In the order of the links to them. The default view is DEFAULT.view. */
export const VIEWS = ["open-issues", "open-prs"] as const;
export type View = (typeof VIEWS)[number];

/** Each view's directory. */
export const VIEW_PATHS: Record<View, string> = { "open-prs": "reviews", "open-issues": "issues" };

/** The Period menu's choices. Only the default, the last year, is relative
 * to the window's end; the others are written to the URL as dates. */
export const PRESETS = ["1y", "3y", "all"] as const;
export type Preset = (typeof PRESETS)[number];

/** Fixed dates, YYYY-MM-DD, inclusive and within the window; or null for
 * the default, the last year counted back from the window's end. */
export type Range = { from: string; to: string } | null;

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

export const DEFAULT: State = {
  view: "open-issues",
  repo: null,
  range: null,
  bin: "auto",
};

/** What a URL is checked against. */
export interface Context {
  repoNames: string[];
  /** The window, YYYY-MM-DD. */
  from: string;
  to: string;
}

function oneOf<T extends string>(values: readonly T[], value: string | null, fallback: T): T {
  return value !== null && (values as readonly string[]).includes(value) ? (value as T) : fallback;
}

const DATE = /^\d{4}-\d{2}-\d{2}$/;

function validDate(value: string | null, ctx: Context): string | null {
  if (value === null || !DATE.test(value) || Number.isNaN(Date.parse(value))) return null;
  if (value < ctx.from) return ctx.from;
  if (value > ctx.to) return ctx.to;
  return value;
}

/** `from` and `to`, either one left out for that end of the window, and
 * clamped to it. Null (the default) if neither, or invalid or backwards. */
function parseRange(q: URLSearchParams, ctx: Context): Range {
  const [from, to] = [q.get("from"), q.get("to")];
  if (from === null && to === null) return null;
  const a = from === null ? ctx.from : validDate(from, ctx);
  const b = to === null ? ctx.to : validDate(to, ctx);
  return a !== null && b !== null && a <= b ? { from: a, to: b } : null;
}

function repoName(value: string | null | undefined, ctx: Context): string | null {
  return ctx.repoNames.find((n) => n === value) ?? null;
}

/**
 * The state for a page's path relative to the site's root ("", the default
 * view; "reviews/", "issues/html/") and a query string. Pages exist only
 * for views and specs (page.ts), so the path is always one; other paths
 * get 404.html. Parameters that are unknown or invalid are left out.
 */
export function parse(path: string, search: string, ctx: Context): State {
  const q = new URLSearchParams(search);
  const [dir, name] = path.split("/");
  return {
    view: VIEWS.find((v) => VIEW_PATHS[v] === dir) ?? DEFAULT.view,
    repo: repoName(name, ctx),
    range: parseRange(q, ctx),
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
  if (state.range !== null) {
    q.set("from", state.range.from);
    q.set("to", state.range.to);
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

const PRESET_MONTHS: Record<Exclude<Preset, "all">, number> = { "3y": 36, "1y": 12 };

/** The first and last day (inclusive, days from ctx.from) a preset covers,
 * counted back from the window's end. */
function presetDays(preset: Preset, ctx: Context): [number, number] {
  const last = dayOf(ctx.from, ctx.to);
  if (preset === "all") return [0, last];
  const end = new Date(`${ctx.to}T00:00:00Z`);
  end.setUTCMonth(end.getUTCMonth() - PRESET_MONTHS[preset]);
  end.setUTCDate(end.getUTCDate() + 1);
  return [Math.max(0, dayOf(ctx.from, end.toISOString().slice(0, 10))), last];
}

/** The range a Period choice sets: null for the default, else its dates. */
export function presetRange(preset: Preset, ctx: Context): Range {
  if (preset === "1y") return null;
  const [a, b] = presetDays(preset, ctx);
  return { from: dateOf(ctx.from, a), to: dateOf(ctx.from, b) };
}

/** The Period choice a range is, or null if its dates are no choice's (a
 * link from before the data was last updated, or edited by hand). */
export function rangePreset(range: Range, ctx: Context): Preset | null {
  if (range === null) return "1y";
  return (
    PRESETS.find((p) => {
      const [a, b] = presetDays(p, ctx);
      return range.from === dateOf(ctx.from, a) && range.to === dateOf(ctx.from, b);
    }) ?? null
  );
}

/** The first and last day (inclusive, days from ctx.from) a range covers. */
export function rangeDays(range: Range, ctx: Context): [number, number] {
  return range === null ? presetDays("1y", ctx) : [dayOf(ctx.from, range.from), dayOf(ctx.from, range.to)];
}
