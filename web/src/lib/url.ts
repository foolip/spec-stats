// The URL is the view (docs/site-design.md, "The URL is the view"): the
// view and the spec are in the path, so each has its own prerendered page
// (reviews/, reviews/html/, issues/html/), and the date range and the bars' period are in
// the query string, defaults left out. parse() reads a path and query
// string into a whole, valid state, dropping what it doesn't understand;
// href() writes the state back. Paths are relative to the site's root.

import { BINS, type Bin } from "./bins.ts";
import { dayOf } from "./data.ts";

/** In the order of the links to them. The default view is DEFAULT.view. */
export const VIEWS = ["open-issues", "open-prs"] as const;
export type View = (typeof VIEWS)[number];

/** Each view's directory. */
export const VIEW_PATHS: Record<View, string> = { "open-prs": "reviews", "open-issues": "issues" };

export const PRESETS = ["all", "3y", "1y"] as const;
export type Preset = (typeof PRESETS)[number];

/** Bars' period: a calendar day, ISO week, month or quarter, or "auto" (the
 * smallest of week, month and quarter that keeps the bars few enough). */
export type BinChoice = Bin | "auto";
export const BIN_CHOICES: readonly BinChoice[] = ["auto", ...BINS];

export interface State {
  view: View;
  /** One repo's name, or null for every repo. A name, not an index, so
   * links survive repos being added. */
  repo: string | null;
  /** The date range, counted back from the window's end. */
  range: Preset;
  bin: BinChoice;
}

export const DEFAULT_PRESET: Preset = "1y";

export const DEFAULT: State = {
  view: "open-issues",
  repo: null,
  range: DEFAULT_PRESET,
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
    range: oneOf(PRESETS, q.get("range"), DEFAULT_PRESET),
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
  if (state.range !== DEFAULT_PRESET) q.set("range", state.range);
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

/** The first and last day (inclusive, days from ctx.from) a range covers. */
export function rangeDays(range: Preset, ctx: Context): [number, number] {
  const last = dayOf(ctx.from, ctx.to);
  if (range === "all") return [0, last];
  const end = new Date(`${ctx.to}T00:00:00Z`);
  end.setUTCMonth(end.getUTCMonth() - PRESET_MONTHS[range]);
  end.setUTCDate(end.getUTCDate() + 1);
  return [Math.max(0, dayOf(ctx.from, end.toISOString().slice(0, 10))), last];
}
