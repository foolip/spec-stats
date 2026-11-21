<script lang="ts">
  // PRs merged, or issues closed, per period, by time open: the chart and
  // its table. Prerendered with the chart's box empty.
  import StackedBars from "../components/StackedBars.svelte";
  import { periodName } from "../lib/bins.ts";
  import { BARS_HEIGHT } from "../lib/chart.ts";
  import { num } from "../lib/format.ts";
  import { capitalized } from "../lib/texts.ts";
  import type { IslandProps } from "./index.ts";

  let { model, width }: IslandProps = $props();
  const t = $derived(model.text);
  const w = $derived(model.words);
</script>

<section class="panel">
  <div class="panel-head">
    <h2>{capitalized(w.items)} {w.done} per {t.unit}, by time open</h2>
    <ul class="legend">
      {#each model.flowBands as l (l.label)}
        <li><span class="swatch" style:background={l.color}></span>{l.label}</li>
      {/each}
    </ul>
  </div>
  <div class="chart-box" style:height="{BARS_HEIGHT}px">
    {#if width !== undefined}
      <StackedBars from={model.data.from} start={t.start} end={t.end} periods={model.flowPeriods}
        name={(p) => periodName(p, t.bin)} layers={model.flowLayers} label="{capitalized(w.items)} {w.done} per {t.unit}"
        done={w.done} height={BARS_HEIGHT} {width} />
    {/if}
  </div>
  <details class="table-view">
    <summary>Table: {w.doneNoun} per {t.unit}</summary>
    <table>
      <thead>
        <tr>
          <th scope="col">{t.unitTitle}</th>
          {#each model.flowBands as l (l.label)}<th scope="col">{l.label}</th>{/each}
          <th scope="col">{capitalized(w.done)}</th>
        </tr>
      </thead>
      <tbody>
        {#each [...model.flowPeriods.keys()].reverse() as j (j)}
          <tr>
            <td>{periodName(model.flowPeriods[j], t.bin)}{model.flowPeriods[j].partial ? " (partial)" : ""}</td>
            {#each model.flowCounts[j] as c, k (k)}<td>{num(c)}</td>{/each}
            <td>{num(model.flowCounts[j].reduce((a, b) => a + b, 0))}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </details>
</section>
