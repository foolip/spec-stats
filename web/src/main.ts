// The parts of the page that need the data (docs/site-design.md,
// "Loading"): once the data has loaded, each element marked data-island is
// emptied and its component (src/islands/) mounted there, in one task, so
// nothing is painted in between. They then follow the controller's state.

import { flushSync, mount } from "svelte";
import { islands, type IslandName } from "./islands/index.ts";
import { load } from "./lib/data.ts";
import { Model } from "./lib/model.svelte.ts";
import { viewState } from "./lib/view.svelte.ts";

const controller = window.specstats;

load(controller.data).then(
  (data) => {
    const model = new Model(data, viewState(controller));
    for (const el of document.querySelectorAll<HTMLElement>("[data-island]")) {
      const width = el.clientWidth;
      el.replaceChildren();
      mount(islands[el.dataset.island as IslandName], { target: el, props: { model, width } });
    }
    flushSync();
    controller.ready();
  },
  (e: unknown) => controller.fail(`Couldn’t load the data: ${String(e)}`),
);
