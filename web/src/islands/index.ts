// The parts of the page that change with the state, other than the
// controls (docs/site-design.md, "Loading"): one per section, by the name
// in its element's data-island attribute. Page.svelte prerenders them
// from here (the charts as empty boxes), and main.ts mounts them from here
// once the data has loaded, so the names can't drift apart.

import type { Component } from "svelte";
import type { Model } from "../lib/model.svelte.ts";
import BySpec from "./BySpec.svelte";
import FlowPanel from "./FlowPanel.svelte";
import OpenedPanel from "./OpenedPanel.svelte";
import OpenPanel from "./OpenPanel.svelte";
import Summary from "./Summary.svelte";

export interface IslandProps {
  model: Model;
  /** The island's width, measured before mounting, for its chart. Absent
   * when prerendering, where the chart's box is left empty. */
  width?: number;
}

export const islands = {
  summary: Summary,
  openPanel: OpenPanel,
  flowPanel: FlowPanel,
  openedPanel: OpenedPanel,
  bySpec: BySpec,
} satisfies Record<string, Component<IslandProps>>;

export type IslandName = keyof typeof islands;
