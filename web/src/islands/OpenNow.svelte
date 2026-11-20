<script lang="ts">
  // The first tile's value: PRs open at the end of the range.
  import { num } from "../lib/format.ts";
  import type { IslandProps } from "./index.ts";

  let { model }: IslandProps = $props();
</script>

<div class="tile-value">{num(model.now)}</div>
