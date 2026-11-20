<script lang="ts">
  // The open PRs table's rows: the month ends in the range, newest first.
  import { longDate, num } from "../lib/format.ts";
  import type { IslandProps } from "./index.ts";

  let { model }: IslandProps = $props();
</script>

{#each model.monthly as m (m.date)}
  <tr>
    <td>{longDate(m.date)}</td>
    {#each [...m.values].reverse() as v, k (k)}<td>{num(v)}</td>{/each}
    <td>{num(m.total)}</td>
  </tr>
{/each}
