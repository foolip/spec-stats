<script lang="ts">
  // Open PRs or issues at the end of each period, by year opened: the chart
  // and its table of month ends. Prerendered with the chart's box empty.
  import StackedArea from "../components/StackedArea.svelte";
  import { AREA_HEIGHT } from "../lib/chart.ts";
  import { longDate, num } from "../lib/format.ts";
  import type { IslandProps } from "./index.ts";

  let { model, width }: IslandProps = $props();
  const layers = $derived([...model.layers].reverse());
</script>

<section class="panel">
  <div class="panel-head">
    <h2>Open {model.words.items} at the end of each {model.text.unit}, by year opened</h2>
    <ul class="legend">
      {#each layers as l (l.label)}
        <li><span class="swatch" style:background={l.color}></span>{l.label}</li>
      {/each}
    </ul>
  </div>
  <div class="chart-box" style:height="{AREA_HEIGHT}px">
    {#if width !== undefined}
      <StackedArea from={model.data.from} start={model.text.start} end={model.text.end} layers={model.layers}
        sample={model.sample} label="Open {model.words.items} by year opened" height={AREA_HEIGHT} {width} />
    {/if}
  </div>
  <details class="table-view">
    <summary>Table: month ends</summary>
    <table>
      <thead>
        <tr>
          <th scope="col">Date</th>
          {#each layers as l (l.label)}<th scope="col">{l.label}</th>{/each}
          <th scope="col">Open</th>
        </tr>
      </thead>
      <tbody>
        {#each model.monthly as m (m.date)}
          <tr>
            <td>{longDate(m.date)}</td>
            {#each [...m.values].reverse() as v, k (k)}<td>{num(v)}</td>{/each}
            <td>{num(m.total)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </details>
</section>
