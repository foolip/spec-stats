<script lang="ts" module>
  /** The parts of the page that need the data. Each is prerendered into
   * an element with data-island="name" (the charts as empty boxes of their
   * final size) and mounted there by main.ts once the data has loaded. */
  export type IslandName = "now" | "change" | "merged" | "area" | "monthly" | "bars" | "merges" | "by-spec";
</script>

<script lang="ts">
  import StackedArea from "./components/StackedArea.svelte";
  import StackedBars from "./components/StackedBars.svelte";
  import { AREA_HEIGHT, BARS_HEIGHT } from "./lib/chart.ts";
  import { longDate, num, signed } from "./lib/format.ts";
  import type { Model } from "./lib/model.svelte.ts";
  import { periodName } from "./lib/bins.ts";

  interface Props {
    name: IslandName;
    model: Model;
    /** The charts' width, measured from their box before mounting. */
    width?: number;
  }
  let { name, model, width = 720 }: Props = $props();
</script>

{#if name === "now"}
  <div class="tile-value">{num(model.now)}</div>
{:else if name === "change"}
  <div class="tile-value" class:up={model.change > 0} class:down={model.change < 0}>{signed(model.change)}</div>
  <div class="tile-note">from {num(model.startOpen)}</div>
{:else if name === "merged"}
  <div class="tile-value">{num(model.merged)}</div>
{:else if name === "area"}
  <StackedArea from={model.data.from} start={model.text.start} end={model.text.end} layers={model.layers}
    sample={model.sample} label="Open PRs by year opened" height={AREA_HEIGHT} {width} />
{:else if name === "monthly"}
  {#each model.monthly as m (m.date)}
    <tr>
      <td>{longDate(m.date)}</td>
      {#each [...m.values].reverse() as v, k (k)}<td>{num(v)}</td>{/each}
      <td>{num(m.total)}</td>
    </tr>
  {/each}
{:else if name === "bars"}
  <StackedBars from={model.data.from} start={model.text.start} end={model.text.end} periods={model.mergePeriods}
    name={(p) => periodName(p, model.text.bin)} layers={model.mergeLayers} label="PRs merged per {model.text.unit}"
    height={BARS_HEIGHT} {width} />
{:else if name === "merges"}
  {#each [...model.mergePeriods.keys()].reverse() as j (j)}
    <tr>
      <td>{periodName(model.mergePeriods[j], model.text.bin)}{model.mergePeriods[j].partial ? " (partial)" : ""}</td>
      {#each model.mergeCounts[j] as c, k (k)}<td>{num(c)}</td>{/each}
      <td>{num(model.mergeCounts[j].reduce((a, b) => a + b, 0))}</td>
    </tr>
  {/each}
{:else if name === "by-spec"}
  <!-- With one spec, the table would only repeat the tiles. -->
  {#if model.rows.length > 1}
    <section class="panel">
      <h2>By spec</h2>
      <table class="by-spec">
        <thead>
          <tr>
            <th scope="col">Spec</th>
            <th scope="col" class="n">Open</th>
            <th scope="col" class="n">Change</th>
            <th scope="col" class="bar-col"><span class="visually-hidden">Open, as a bar</span></th>
          </tr>
        </thead>
        <tbody>
          {#each model.rows as row (row.name)}
            <tr>
              <th scope="row">
                <!-- The controller handles the click. -->
                <button type="button" class="spec" title="Show only {row.standard}" data-repo={row.name}>{row.standard}</button>
              </th>
              <td class="n">{num(row.open)}</td>
              <td class="n" class:up={row.change > 0} class:down={row.change < 0}>{signed(row.change)}</td>
              <td class="bar-col"><span class="bar" style:width="{(row.open / model.maxOpen) * 100}%"></span></td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>
  {/if}
{/if}
