<script lang="ts">
  // The by-spec table, most open PRs first. It's shown for all specs only;
  // the controller hides its section otherwise.
  import { num, signed } from "../lib/format.ts";
  import type { IslandProps } from "./index.ts";

  let { model }: IslandProps = $props();
</script>

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
