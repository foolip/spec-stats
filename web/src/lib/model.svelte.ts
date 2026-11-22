// Everything a view shows that needs the data, derived from the data and
// the state: open PRs and merges for the open PRs view, open issues and
// closes for the open issues view. Used on the server to prerender a page
// and in the browser, where the state follows the controller, the view
// included: switching views recomputes from the data in memory.

import { periods, sampleDays } from "./bins.ts";
import type { Layer } from "../components/StackedArea.svelte";
import type { BarLayer } from "../components/StackedBars.svelte";
import { dateOf, type Data } from "./data.ts";
import { closes, flowByPeriod, merges, type Flow } from "./flow.ts";
import { ofKind, openByGroup, openByRepo, total, yearCohorts, type Cohorts, type Kind, type OpenSeries } from "./open.ts";
import { stateText, VIEW_TEXT } from "./texts.ts";
import { selectedRepos, type Context, type State } from "./url.ts";

/** What a view counts, over the whole window and every repo. */
interface Counts {
  byRepo: OpenSeries[];
  /** By repo, then by year opened (Model.cohorts). */
  byCohort: OpenSeries[][];
  /** Merges or closes. */
  flow: Flow;
}

export class Model {
  data: Data;
  /** Reactive in the browser. */
  view: State;
  ctx: Context;
  /** Items by the year they were opened, oldest first. */
  cohorts: Cohorts;
  /** Each kind's counts, worked out the first time its view is shown. */
  #counts = new Map<Kind, Counts>();

  constructor(data: Data, view: State) {
    this.data = data;
    this.view = view;
    this.ctx = { repoNames: data.repos.name, from: data.from, to: data.to };
    this.cohorts = yearCohorts(data);
  }

  #countsOf(kind: Kind): Counts {
    let c = this.#counts.get(kind);
    if (!c) {
      const mine = ofKind(this.data, kind);
      const of = this.cohorts.of.map((g, i) => (mine[i] < 0 ? -1 : g));
      c = {
        byRepo: openByRepo(this.data, kind),
        byCohort: openByGroup(this.data, of, this.cohorts.labels.length),
        flow: kind === "issue" ? closes(this.data) : merges(this.data),
      };
      this.#counts.set(kind, c);
    }
    return c;
  }

  kind: Kind = $derived.by(() => (this.view.view === "open-issues" ? "issue" : "pr"));
  /** The view's words: "PRs", "merged". */
  words = $derived.by(() => VIEW_TEXT[this.view.view]);
  #c = $derived.by(() => this.#countsOf(this.kind));
  byRepo = $derived.by(() => this.#c.byRepo);
  byCohort = $derived.by(() => this.#c.byCohort);
  flow = $derived.by(() => this.#c.flow);

  text = $derived.by(() => stateText(this.view, this.ctx));
  repos = $derived.by(() => selectedRepos(this.view.repo, this.data.repos.name));
  series = $derived.by(() => total(this.byRepo, this.repos, this.data.days));

  /** Open items by year opened, oldest at the bottom. Drafts aren't
   * counted: only PRs ready for review (and every open issue). */
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

  /** PRs merged, or issues closed, per calendar period. */
  flowPeriods = $derived.by(() => periods(this.data.from, this.text.start, this.text.end, this.text.bin));
  flowCounts = $derived.by(() => flowByPeriod(this.data, this.flow, this.repos, this.flowPeriods));
  /** Fastest first, for the legend and the table; stacked the other way,
   * so the slowest is at the bottom and the fastest (lightest) on top, as
   * the open items' newest layer is. */
  flowBands: BarLayer[] = $derived.by(() =>
    this.flow.bands.labels.map((label, k) => ({
      label,
      values: this.flowCounts.map((c) => c[k]),
      color: `var(--age-${k})`,
    })),
  );
  flowLayers = $derived.by(() => [...this.flowBands].reverse());
  done = $derived.by(() => this.flowCounts.reduce((s, c) => s + c.reduce((a, b) => a + b, 0), 0));
  /** The open PRs are drawn at the same periods' ends, so they follow the
   * bin too: every day, or the last day of each week, month or quarter. */
  sample = $derived.by(() => sampleDays(this.flowPeriods));

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
      .sort((a, b) => b.open - a.open || a.standard.localeCompare(b.standard)),
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
