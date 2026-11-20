<script lang="ts">
  // The merges table's rows: one per period, newest first.
  import { periodName } from "../lib/bins.ts";
  import { num } from "../lib/format.ts";
  import type { IslandProps } from "./index.ts";

  let { model }: IslandProps = $props();
</script>

{#each [...model.mergePeriods.keys()].reverse() as j (j)}
  <tr>
    <td>{periodName(model.mergePeriods[j], model.text.bin)}{model.mergePeriods[j].partial ? " (partial)" : ""}</td>
    {#each model.mergeCounts[j] as c, k (k)}<td>{num(c)}</td>{/each}
    <td>{num(model.mergeCounts[j].reduce((a, b) => a + b, 0))}</td>
  </tr>
{/each}
