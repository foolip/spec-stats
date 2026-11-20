<script lang="ts">
  // The third tile's value: PRs merged in the range.
  import { num } from "../lib/format.ts";
  import type { IslandProps } from "./index.ts";

  let { model }: IslandProps = $props();
</script>

<div class="tile-value">{num(model.merged)}</div>
