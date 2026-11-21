<script lang="ts">
  // The summary tiles: the PRs open at the end of the range, the change
  // over it, and the PRs merged in it.
  import { num, signed } from "../lib/format.ts";
  import type { IslandProps } from "./index.ts";

  let { model }: IslandProps = $props();
  const t = $derived(model.text);
</script>

<section class="tiles" aria-label="Summary">
  <div class="tile">
    <div class="tile-label">Open on {t.endDate}</div>
    <div class="tile-value">{num(model.now)}</div>
  </div>
  <div class="tile">
    <div class="tile-label">Change since {t.startDate}</div>
    <div class="tile-value" class:up={model.change > 0} class:down={model.change < 0}>{signed(model.change)}</div>
    <div class="tile-note">from {num(model.startOpen)}</div>
  </div>
  <div class="tile">
    <div class="tile-label">Merged since {t.startDate}</div>
    <div class="tile-value">{num(model.merged)}</div>
  </div>
</section>
