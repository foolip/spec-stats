<script lang="ts">
  // PRs merged per period, by time open: the chart and its table.
  // Prerendered with the chart's box empty.
  import StackedBars from "../components/StackedBars.svelte";
  import { periodName } from "../lib/bins.ts";
  import { BARS_HEIGHT } from "../lib/chart.ts";
  import { num } from "../lib/format.ts";
  import type { IslandProps } from "./index.ts";

  let { model, width }: IslandProps = $props();
  const t = $derived(model.text);
</script>

<section class="panel">
  <div class="panel-head">
    <h2>PRs merged per {t.unit}, by time open</h2>
    <ul class="legend">
      {#each model.mergeBands as l (l.label)}
        <li><span class="swatch" style:background={l.color}></span>{l.label}</li>
      {/each}
    </ul>
  </div>
  <div class="chart-box" style:height="{BARS_HEIGHT}px">
    {#if width !== undefined}
      <StackedBars from={model.data.from} start={t.start} end={t.end} periods={model.mergePeriods}
        name={(p) => periodName(p, t.bin)} layers={model.mergeLayers} label="PRs merged per {t.unit}"
        height={BARS_HEIGHT} {width} />
    {/if}
  </div>
  <details class="table-view">
    <summary>Table: merges per {t.unit}</summary>
    <table>
      <thead>
        <tr>
          <th scope="col">{t.unitTitle}</th>
          {#each model.mergeBands as l (l.label)}<th scope="col">{l.label}</th>{/each}
          <th scope="col">Merged</th>
        </tr>
      </thead>
      <tbody>
        {#each [...model.mergePeriods.keys()].reverse() as j (j)}
          <tr>
            <td>{periodName(model.mergePeriods[j], t.bin)}{model.mergePeriods[j].partial ? " (partial)" : ""}</td>
            {#each model.mergeCounts[j] as c, k (k)}<td>{num(c)}</td>{/each}
            <td>{num(model.mergeCounts[j].reduce((a, b) => a + b, 0))}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </details>
</section>
