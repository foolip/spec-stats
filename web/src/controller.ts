// The page's controller (docs/site-design.md, "Loading"): plain TypeScript,
// built into a small script that's inlined into every prerendered page,
// after the view and before the footer. The page's
// `<link rel="expect" href="#footer" blocking="render">` holds the first
// paint until the footer is parsed, so this has run by then. It owns the
// URL and the form controls for the life of the page: it reads the state
// from the URL, sets the controls and handles their events. Everything
// else that changes with the state is a Svelte island (src/islands/),
// mounted by main.ts once the data has loaded; until then, if the URL
// isn't the one the page was prerendered for, the islands are hidden
// (`data-pending`), keeping their space. Switching views happens here too,
// without loading a page: the view links push a history entry, and the
// view's title and question are set from lib/texts.ts.

import type { PageConfig } from "./lib/config.ts";
import { pageTitle, stateText, VIEW_TEXT } from "./lib/texts.ts";
import { fixed, href, parse, type BinChoice, type Context, type Preset, type State, type View } from "./lib/url.ts";

export interface Controller {
  readonly state: State;
  readonly ctx: Context;
  /** The data file's URL. */
  readonly data: string;
  /** Called after every change of state. */
  subscribe(listener: (state: State) => void): void;
  /** Change the state, as a control does. */
  set(change: Partial<State>): void;
  /** The parts that need the data are showing the current state. */
  ready(): void;
  /** The data couldn't be loaded. */
  fail(message: string): void;
}

declare global {
  interface Window {
    specstats: Controller;
  }
}

const config = JSON.parse(document.getElementById("config")!.textContent!) as PageConfig;
const ctx: Context = { repoNames: config.repos, from: config.from, to: config.to };
const root = new URL(config.root, location.href);
const html = document.documentElement;
const listeners: ((state: State) => void)[] = [];
let ready = false;

function control<T extends HTMLElement>(name: string): T {
  return document.querySelector<T>(`[data-control="${name}"]`)!;
}
const repoSelect = control<HTMLSelectElement>("repo");
const presets = [...document.querySelectorAll<HTMLButtonElement>("[data-preset]")];
const binSelect = control<HTMLSelectElement>("bin");
const copy = control<HTMLButtonElement>("copy");
const status = control<HTMLElement>("status");
const viewLinks = [...document.querySelectorAll<HTMLAnchorElement>("a[data-view]")];
const title = control<HTMLElement>("title");
const question = control<HTMLElement>("question");

/** The state in the URL: the path from the site's root, and the query. */
function fromUrl(): State {
  const path = location.pathname.startsWith(root.pathname) ? location.pathname.slice(root.pathname.length) : "";
  return parse(decodeURIComponent(path), location.search, ctx);
}

let state = fromUrl();

/** Show the state: the controls, the title, and whether the islands'
 * prerendered content is hidden. */
function apply() {
  const t = stateText(state, ctx);
  repoSelect.value = state.repo ?? "";
  for (const b of presets) b.setAttribute("aria-pressed", String("preset" in state.range && state.range.preset === b.dataset.preset));
  binSelect.value = state.bin;
  binSelect.options[0].text = t.autoLabel;
  // The views, with the same spec and query string.
  for (const a of viewLinks) {
    a.href = new URL(href({ ...state, view: a.dataset.view as View }), root).href;
    if (a.dataset.view === state.view) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
  title.textContent = VIEW_TEXT[state.view].title;
  question.textContent = VIEW_TEXT[state.view].question;
  const r = state.repo === null ? -1 : config.repos.indexOf(state.repo);
  document.title = pageTitle(state.view, r < 0 ? null : config.standards[r]);
  html.toggleAttribute("data-pending", !ready && href(state) !== config.prerendered);
}

/** Change the state; a new history entry only if `push` (a view change),
 * so dragging a range doesn't fill the back button. */
function update(next: State, push = false) {
  state = next;
  const url = new URL(href(state), root);
  if (url.href !== location.href) history[push ? "pushState" : "replaceState"](null, "", url);
  apply();
  for (const f of listeners) f(state);
}

function set(change: Partial<State>) {
  update({ ...state, ...change });
}

// The URL as it should be: anything not understood dropped (url.ts).
update(state);
addEventListener("popstate", () => update(fromUrl()));

repoSelect.addEventListener("change", () => set({ repo: repoSelect.value || null }));
for (const b of presets) b.addEventListener("click", () => set({ range: { preset: b.dataset.preset as Preset } }));
binSelect.addEventListener("change", () => set({ bin: binSelect.value as BinChoice }));
for (const a of viewLinks) {
  a.addEventListener("click", (e) => {
    // A new tab or window, or a download, as for any link.
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    const view = a.dataset.view as View;
    if (view !== state.view) update({ ...state, view }, true);
  });
}

// Copy link: the label swaps in place (both labels share one grid cell, so
// the button keeps its width), and the live region announces it.
let copiedTimer: ReturnType<typeof setTimeout> | undefined;
function copied(on: boolean) {
  const [label, done] = copy.children;
  label.classList.toggle("hidden", on);
  done.classList.toggle("hidden", !on);
  done.setAttribute("aria-hidden", String(!on));
}
copy.addEventListener("click", async () => {
  const url = new URL(href({ ...state, range: fixed(state.range, ctx) }), root).href;
  try {
    await navigator.clipboard.writeText(url);
    copied(true);
    // VoiceOver skips a message identical to the previous one.
    const message = "Link to this view copied";
    status.textContent = status.textContent === message ? `${message} ` : message;
    clearTimeout(copiedTimer);
    copiedTimer = setTimeout(() => copied(false), 2500);
  } catch {
    prompt("Link to this view", url);
  }
});

window.specstats = {
  get state() {
    return state;
  },
  ctx,
  data: new URL(config.data, root).href,
  subscribe: (listener) => void listeners.push(listener),
  set,
  ready() {
    ready = true;
    apply();
  },
  fail(message) {
    const el = document.querySelector<HTMLElement>("[data-error]")!;
    el.textContent = message;
    el.hidden = false;
  },
};
