<script lang="ts">
  // The merges as a table: one row per period, newest first.
  import { periodName } from "../lib/bins.ts";
  import { num } from "../lib/format.ts";
  import type { IslandProps } from "./index.ts";

  let { model }: IslandProps = $props();
</script>

<table>
  <thead>
    <tr>
      <th scope="col">{model.text.unitTitle}</th>
      {#each model.mergeBands as l (l.label)}<th scope="col">{l.label}</th>{/each}
      <th scope="col">Merged</th>
    </tr>
  </thead>
  <tbody>
    {#each [...model.mergePeriods.keys()].reverse() as j (j)}
      <tr>
        <td>{periodName(model.mergePeriods[j], model.text.bin)}{model.mergePeriods[j].partial ? " (partial)" : ""}</td>
        {#each model.mergeCounts[j] as c, k (k)}<td>{num(c)}</td>{/each}
        <td>{num(model.mergeCounts[j].reduce((a, b) => a + b, 0))}</td>
      </tr>
    {/each}
  </tbody>
</table>
