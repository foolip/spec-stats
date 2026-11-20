<script lang="ts">
  // The open PRs as a table: the month ends in the range, newest first.
  import { longDate, num } from "../lib/format.ts";
  import type { IslandProps } from "./index.ts";

  let { model }: IslandProps = $props();
</script>

<table>
  <thead>
    <tr>
      <th scope="col">Date</th>
      {#each [...model.layers].reverse() as l (l.label)}<th scope="col">{l.label}</th>{/each}
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
