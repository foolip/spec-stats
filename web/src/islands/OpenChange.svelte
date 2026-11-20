<script lang="ts">
  // The second tile's value: the change in open PRs over the range.
  import { num, signed } from "../lib/format.ts";
  import type { IslandProps } from "./index.ts";

  let { model }: IslandProps = $props();
</script>

<div class="tile-value" class:up={model.change > 0} class:down={model.change < 0}>{signed(model.change)}</div>
<div class="tile-note">from {num(model.startOpen)}</div>
