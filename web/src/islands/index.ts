// The parts of the page that need the data (docs/site-design.md,
// "Loading"), by the name in their element's data-island attribute.
// Each is a whole element's content: a value, a chart or a table.
// Page.svelte prerenders them from here (the charts as empty boxes), and
// main.ts mounts them from here once the data has loaded, so the names
// can't drift apart.

import type { Component } from "svelte";
import type { Model } from "../lib/model.svelte.ts";
import BySpecTable from "./BySpecTable.svelte";
import Merged from "./Merged.svelte";
import MergesChart from "./MergesChart.svelte";
import MergesTable from "./MergesTable.svelte";
import OpenChange from "./OpenChange.svelte";
import OpenChart from "./OpenChart.svelte";
import OpenNow from "./OpenNow.svelte";
import OpenTable from "./OpenTable.svelte";

export interface IslandProps {
  model: Model;
  /** The island's box width, measured before mounting: for the charts. */
  width?: number;
}

export const islands = {
  openNow: OpenNow,
  openChange: OpenChange,
  merged: Merged,
  openChart: OpenChart,
  openTable: OpenTable,
  mergesChart: MergesChart,
  mergesTable: MergesTable,
  bySpecTable: BySpecTable,
} satisfies Record<string, Component<IslandProps>>;

export type IslandName = keyof typeof islands;
