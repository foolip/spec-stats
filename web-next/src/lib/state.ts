// The view's state, read from and written to the URL (docs/site-design.md,
// "The URL is the view"): the view and the spec are in the path, the rest in
// the query string, with defaults left out.

import { Calendar } from "./dates.ts";

export const VIEWS = ["issues", "reviews"] as const;
export type View = (typeof VIEWS)[number];
export const DEFAULT_VIEW: View = "issues";

export const BINS = ["auto", "day", "week", "month", "quarter"] as const;
export type Bin = (typeof BINS)[number];

export const PRESETS = ["year", "3years", "all"] as const;
export type Preset = (typeof PRESETS)[number];
export const PRESET_LABELS: Record<Preset, string> = {
  year: "Last year",
  "3years": "Last 3 years",
  all: "All",
};

export interface State {
  view: View;
  /** Repo name, or null for all specs. */
  spec: string | null;
  /** First and last day of the range, as day indexes. */
  from: number;
  to: number;
  bin: Bin;
}

export interface Window {
  from: string;
  to: string;
}

/** The first and last day of a preset range, counted back from the window's end. */
export function presetRange(win: Window, preset: Preset): { from: number; to: number } {
  const cal = new Calendar(win.from);
  const end = cal.day(win.to);
  if (preset === "all") return { from: 0, to: end };
  const years = preset === "year" ? 1 : 3;
  const d = cal.date(end);
  const from = cal.dayOf(d.getUTCFullYear() - years, d.getUTCMonth(), d.getUTCDate() + 1);
  return { from: Math.max(0, from), to: end };
}

/** The preset a range is, or null for a custom range. */
export function presetOf(win: Window, from: number, to: number): Preset | null {
  for (const p of PRESETS) {
    const r = presetRange(win, p);
    if (r.from === from && r.to === to) return p;
  }
  return null;
}

export function defaultState(win: Window, view: View = DEFAULT_VIEW, spec: string | null = null): State {
  return { view, spec, ...presetRange(win, "year"), bin: "auto" };
}

/** Strips the site's base path; returns the path's segments. */
function segments(pathname: string, base: string): string[] {
  let path = pathname;
  if (base && (path === base || path.startsWith(base + "/"))) path = path.slice(base.length);
  return path.split("/").filter(Boolean);
}

/**
 * Reads the state from a URL. Unknown or invalid parameters are dropped;
 * dates outside the window are clamped to it.
 */
export function parseUrl(
  pathname: string,
  search: string,
  win: Window,
  specs: readonly string[],
  base: string,
): State {
  const [first, second] = segments(pathname, base);
  const view = (VIEWS as readonly string[]).includes(first) ? (first as View) : DEFAULT_VIEW;
  const spec = second && specs.includes(second) ? second : null;
  const state = defaultState(win, view, spec);
  const params = new URLSearchParams(search);
  const cal = new Calendar(win.from);
  const end = cal.day(win.to);
  const clamp = (d: number) => Math.min(end, Math.max(0, d));
  const from = cal.day(params.get("from") ?? "");
  const to = cal.day(params.get("to") ?? "");
  if (!Number.isNaN(from) || !Number.isNaN(to)) {
    let f = Number.isNaN(from) ? 0 : clamp(from);
    let t = Number.isNaN(to) ? end : clamp(to);
    if (f > t) [f, t] = [t, f];
    state.from = f;
    state.to = t;
  }
  const bin = params.get("bin");
  if (bin && (BINS as readonly string[]).includes(bin)) state.bin = bin as Bin;
  return state;
}

/** The path and query string of a state, relative to the host, defaults left out. */
export function formatUrl(state: State, win: Window, base: string): string {
  let path = `${base}/${state.view}/`;
  if (state.spec) path += `${state.spec}/`;
  const params = new URLSearchParams();
  if (presetOf(win, state.from, state.to) !== "year") {
    const cal = new Calendar(win.from);
    params.set("from", cal.iso(state.from));
    params.set("to", cal.iso(state.to));
  }
  if (state.bin !== "auto") params.set("bin", state.bin);
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}
