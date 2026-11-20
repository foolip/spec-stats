// The page's controller (docs/site-design.md, "Loading"): plain TypeScript,
// built into a small script that's inlined into the <head> of every
// prerendered page. It owns the URL and the form controls for the life of
// the page: it reads the state from the URL, sets the controls and the
// texts that need no data, and handles the controls' events. The parts
// that need the data are Svelte components, mounted by main.ts once the
// data has loaded; until then, if the URL isn't the one the page was
// prerendered for, they're hidden (`data-pending`), keeping their space.
//
// It runs before the body is parsed, so it can't wait for the elements:
// a MutationObserver applies the state as the parser adds them. Its
// callbacks run at the end of each parser task, before anything can be
// painted, so no paint shows the prerendered state where the URL asks for
// another. The controls' events are handled on the document.

import type { PageConfig } from "./lib/config.ts";
import { pageTitle, stateText } from "./lib/texts.ts";
import { fixed, href, parse, type BinChoice, type Context, type Preset, type State } from "./lib/url.ts";

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
const root = new URL(document.baseURI);
const html = document.documentElement;
const listeners: ((state: State) => void)[] = [];
let ready = false;

/** A control, or null if it isn't parsed yet. */
function control<T extends HTMLElement>(name: string): T | null {
  return document.querySelector<T>(`[data-control="${name}"]`);
}

/** The state in the URL: the path from the site's root, and the query. */
function fromUrl(): State {
  const path = location.pathname.startsWith(root.pathname) ? location.pathname.slice(root.pathname.length) : "";
  return parse(decodeURIComponent(path), location.search, ctx);
}

let state = fromUrl();

/** Show the state, on whatever of the page is parsed so far: the controls,
 * the texts, the title and whether the prerendered values are hidden. */
function apply() {
  const t = stateText(state, ctx);
  html.toggleAttribute("data-pending", !ready && href(state) !== config.prerendered);
  const r = state.repo === null ? -1 : config.repos.indexOf(state.repo);
  document.title = pageTitle(r < 0 ? null : config.standards[r]);
  const repo = control<HTMLSelectElement>("repo");
  if (repo) repo.value = state.repo ?? "";
  for (const b of document.querySelectorAll<HTMLElement>("[data-preset]")) {
    b.setAttribute("aria-pressed", String("preset" in state.range && state.range.preset === b.dataset.preset));
  }
  const custom = control("custom");
  if (custom) {
    custom.toggleAttribute("data-active", "from" in state.range);
    custom.textContent = t.customLabel;
  }
  const from = control<HTMLInputElement>("from");
  if (from) Object.assign(from, { value: t.dates.from, max: t.dates.to });
  const to = control<HTMLInputElement>("to");
  if (to) Object.assign(to, { value: t.dates.to, min: t.dates.from });
  const bin = control<HTMLSelectElement>("bin");
  if (bin) {
    bin.value = state.bin;
    if (bin.options[0]) bin.options[0].text = t.autoLabel;
  }
  const texts: Record<string, string> = { start: t.startDate, end: t.endDate, unit: t.unit, "unit-title": t.unitTitle };
  for (const el of document.querySelectorAll<HTMLElement>("[data-text]")) el.textContent = texts[el.dataset.text!];
}

const parsing = new MutationObserver(() => {
  apply();
  parsing.takeRecords(); // apply()'s own changes
});
parsing.observe(document, { childList: true, subtree: true });
document.addEventListener("DOMContentLoaded", () => {
  parsing.disconnect();
  apply();
});

function update(next: State) {
  state = next;
  const url = new URL(href(state), root);
  if (url.href !== location.href) history.replaceState(null, "", url);
  apply();
  for (const f of listeners) f(state);
}

function set(change: Partial<State>) {
  update({ ...state, ...change });
}

// The URL as it should be: old links rewritten, and anything not
// understood dropped (url.ts).
update(state);
addEventListener("popstate", () => update(fromUrl()));

document.addEventListener("change", (e) => {
  const el = e.target as HTMLInputElement | HTMLSelectElement;
  switch (el.dataset.control) {
    case "repo":
      return set({ repo: el.value || null });
    case "bin":
      return set({ bin: el.value as BinChoice });
    case "from":
    case "to": {
      const from = control<HTMLInputElement>("from")!.value || ctx.from;
      const to = control<HTMLInputElement>("to")!.value || ctx.to;
      if (from <= to) set({ range: { from, to } });
    }
  }
});

document.addEventListener("click", (e) => {
  const el = (e.target as Element).closest<HTMLElement>("[data-preset], [data-control=copy], button[data-repo]");
  if (!el) return;
  if (el.dataset.preset) set({ range: { preset: el.dataset.preset as Preset } });
  // The by-spec table's spec names show only that spec.
  else if (el.dataset.repo) set({ repo: el.dataset.repo });
  else copyLink(el);
});

// Copy link: the label swaps in place (both labels share one grid cell, so
// the button keeps its width), and the live region announces it.
let copiedTimer: ReturnType<typeof setTimeout> | undefined;
function copied(button: HTMLElement, on: boolean) {
  const [label, done] = button.children;
  label.classList.toggle("hidden", on);
  done.classList.toggle("hidden", !on);
  done.setAttribute("aria-hidden", String(!on));
}
async function copyLink(button: HTMLElement) {
  const url = new URL(href({ ...state, range: fixed(state.range, ctx) }), root).href;
  try {
    await navigator.clipboard.writeText(url);
    copied(button, true);
    // VoiceOver skips a message identical to the previous one.
    const status = control("status")!;
    const message = "Link to this view copied";
    status.textContent = status.textContent === message ? `${message} ` : message;
    clearTimeout(copiedTimer);
    copiedTimer = setTimeout(() => copied(button, false), 2500);
  } catch {
    prompt("Link to this view", url);
  }
}

// The custom dates menu is a native popover. On wide screens it's placed
// under its button with CSS anchor positioning, or here where that isn't
// supported (Firefox, in November 2026); on narrow screens it's a bottom
// sheet.
const anchored = CSS.supports("position-area: block-end");
let menu: HTMLElement | null = null;
function place() {
  const custom = control("custom");
  if (!menu || !custom) return;
  if (anchored || matchMedia("(max-width: 640px)").matches) {
    menu.style.removeProperty("left");
    menu.style.removeProperty("top");
    return;
  }
  const r = custom.getBoundingClientRect();
  menu.style.left = `${Math.max(8, Math.min(r.left, innerWidth - menu.offsetWidth - 8))}px`;
  menu.style.top = `${r.bottom + 6}px`;
}
// toggle doesn't bubble: listen in the capture phase.
document.addEventListener(
  "toggle",
  (e) => {
    const custom = control("custom");
    if (!custom || (e.target as Element).id !== custom.getAttribute("popovertarget")) return;
    menu = e.target as HTMLElement;
    const open = (e as ToggleEvent).newState === "open";
    custom.setAttribute("aria-expanded", String(open));
    if (open) place();
    if (anchored) return;
    const listen = open ? addEventListener : removeEventListener;
    listen("resize", place);
    listen("scroll", place, true);
  },
  true,
);

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
