<script lang="ts">
  // Open PRs by spec, most first, for all specs only: with one, it would
  // only repeat the tiles.
  import { num, signed } from "../lib/format.ts";
  import type { IslandProps } from "./index.ts";

  let { model }: IslandProps = $props();
</script>

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
              <button type="button" class="spec" title="Show only {row.standard}"
                onclick={() => window.specstats.set({ repo: row.name })}>{row.standard}</button>
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
