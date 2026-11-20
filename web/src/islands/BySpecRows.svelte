<script lang="ts">
  // The by-spec table's rows, most open PRs first. The table is shown only
  // for all specs; the controller hides it otherwise.
  import { num, signed } from "../lib/format.ts";
  import type { IslandProps } from "./index.ts";

  let { model }: IslandProps = $props();
</script>

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
