// Everything the open PRs view shows that needs the data, derived from the
// data and the state. Used on the server to prerender a page and in the
// browser, where the state follows the controller.

import { periods, sampleDays } from "./bins.ts";
import type { Layer } from "../components/StackedArea.svelte";
import type { BarLayer } from "../components/StackedBars.svelte";
import { dateOf, type Data } from "./data.ts";
import { compareText } from "./format.ts";
import { BAND_LABELS, mergesByPeriod } from "./merges.ts";
import { openByGroup, openByRepo, total, yearCohorts, type Cohorts, type OpenSeries } from "./openprs.ts";
import { stateText } from "./texts.ts";
import { selectedRepos, type Context, type State } from "./url.ts";

export class Model {
  data: Data;
  /** Reactive in the browser. */
  view: State;
  ctx: Context;
  byRepo: OpenSeries[];
  /** Open PRs by the year they were opened, oldest first. */
  cohorts: Cohorts;
  byCohort: OpenSeries[][];

  constructor(data: Data, view: State) {
    this.data = data;
    this.view = view;
    this.ctx = { repoNames: data.repos.name, from: data.from, to: data.to };
    this.byRepo = openByRepo(data);
    this.cohorts = yearCohorts(data);
    this.byCohort = openByGroup(data, this.cohorts.of, this.cohorts.labels.length);
  }

  text = $derived.by(() => stateText(this.view, this.ctx));
  repos = $derived.by(() => selectedRepos(this.view.repo, this.data.repos.name));
  series = $derived.by(() => total(this.byRepo, this.repos, this.data.days));

  /** Open PRs by year opened, oldest at the bottom. Drafts aren't counted:
   * only PRs ready for review. */
  layers: Layer[] = $derived.by(() =>
    this.cohorts.labels.map((label, g) => {
      const values = new Int32Array(this.data.days);
      for (const r of this.repos) {
        const s = this.byCohort[r][g];
        for (let d = 0; d < this.data.days; d++) values[d] += s.ready[d];
      }
      return { label, values, color: `var(--cohort-${g})` };
    }),
  );

  /** PRs merged per calendar period. */
  mergePeriods = $derived.by(() => periods(this.data.from, this.text.start, this.text.end, this.text.bin));
  mergeCounts = $derived.by(() => mergesByPeriod(this.data, this.repos, this.mergePeriods));
  /** Fastest first, for the legend and the table; stacked the other way,
   * so the slowest is at the bottom and the fastest (lightest) on top, as
   * the open PRs' newest layer is. */
  mergeBands: BarLayer[] = $derived.by(() =>
    BAND_LABELS.map((label, k) => ({ label, values: this.mergeCounts.map((c) => c[k]), color: `var(--age-${k})` })),
  );
  mergeLayers = $derived.by(() => [...this.mergeBands].reverse());
  merged = $derived.by(() => this.mergeCounts.reduce((s, c) => s + c.reduce((a, b) => a + b, 0), 0));
  /** The open PRs are drawn at the same periods' ends, so they follow the
   * bin too: every day, or the last day of each week, month or quarter. */
  sample = $derived.by(() => sampleDays(this.mergePeriods));

  now = $derived.by(() => this.series.ready[this.text.end]);
  startOpen = $derived.by(() => this.series.ready[this.text.start]);
  change = $derived.by(() => this.now - this.startOpen);

  rows = $derived.by(() =>
    this.repos
      .map((r) => ({
        standard: this.data.repos.standard[r],
        name: this.data.repos.name[r],
        open: this.byRepo[r].ready[this.text.end],
        change: this.byRepo[r].ready[this.text.end] - this.byRepo[r].ready[this.text.start],
      }))
      .sort((a, b) => b.open - a.open || compareText(a.standard, b.standard)),
  );
  maxOpen = $derived.by(() => Math.max(1, ...this.rows.map((r) => r.open)));

  /** Month ends in the range, for the area chart's table view. */
  monthly = $derived.by(() => {
    const out: { date: string; values: number[]; total: number }[] = [];
    const { start, end } = this.text;
    for (let d = start; d <= end; d++) {
      const date = dateOf(this.data.from, d);
      const next = dateOf(this.data.from, d + 1);
      if (d === end || next.slice(0, 7) !== date.slice(0, 7)) {
        const values = this.layers.map((l) => l.values[d]);
        out.push({ date, values, total: values.reduce((a, b) => a + b, 0) });
      }
    }
    return out.reverse();
  });
}
