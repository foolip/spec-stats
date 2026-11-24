<script lang="ts">
  // A panel of stacked bars per period, split into bands: heading, legend,
  // chart and table. Prerendered with the chart's box empty (no `width`).
  import StackedBars, { type BarLayer } from "./StackedBars.svelte";
  import { periodNote, type Bin, type Period } from "../lib/bins.ts";
  import { periodName } from "../lib/names.ts";
  import { BARS_HEIGHT } from "../lib/chart.ts";
  import { num } from "../lib/format.ts";
  import { capitalized } from "../lib/texts.ts";

  interface Props {
    heading: string;
    /** The chart's accessible name: "PRs merged per ISO week". */
    label: string;
    /** The table's summary: "Table: merges per ISO week". */
    summary: string;
    /** What the bars count, for the totals: "merged". */
    done: string;
    from: string;
    start: number;
    end: number;
    bin: Bin;
    unitTitle: string;
    periods: Period[];
    /** counts[period][band], fastest first. */
    counts: number[][];
    /** Fastest first, for the legend and the table. */
    bands: BarLayer[];
    width?: number;
  }
  let { heading, label, summary, done, from, start, end, bin, unitTitle, periods, counts, bands, width }: Props =
    $props();
  // Stacked the other way, so the slowest is at the bottom and the fastest
  // (lightest) on top, as the open items' newest layer is.
  const layers = $derived([...bands].reverse());
</script>

<section class="panel">
  <div class="panel-head">
    <h2>{heading}</h2>
    <ul class="legend">
      {#each bands as l (l.label)}
        <li><span class="swatch" style:background={l.color}></span>{l.label}</li>
      {/each}
    </ul>
  </div>
  <div class="chart-box" style:height="{BARS_HEIGHT}px">
    {#if width !== undefined}
      <StackedBars {from} {start} {end} {periods} name={(p) => periodName(p, bin)} {layers} {label} {done}
        height={BARS_HEIGHT} {width} />
    {/if}
  </div>
  <details class="table-view">
    <summary>{summary}</summary>
    <table>
      <thead>
        <tr>
          <th scope="col">{unitTitle}</th>
          {#each bands as l (l.label)}<th scope="col">{l.label}</th>{/each}
          <th scope="col">{capitalized(done)}</th>
        </tr>
      </thead>
      <tbody>
        {#each [...periods.keys()].reverse() as j (j)}
          <tr>
            <td>{periodName(periods[j], bin)}{periodNote(periods[j])}</td>
            {#each counts[j] as c, k (k)}<td>{num(c)}</td>{/each}
            <td>{num(counts[j].reduce((a, b) => a + b, 0))}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </details>
</section>
