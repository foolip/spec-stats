<script lang="ts">
  // Open PRs by year opened, drawn into its box once the data has loaded.
  import StackedArea from "../components/StackedArea.svelte";
  import { AREA_HEIGHT } from "../lib/chart.ts";
  import type { IslandProps } from "./index.ts";

  let { model, width }: IslandProps = $props();
</script>

<StackedArea from={model.data.from} start={model.text.start} end={model.text.end} layers={model.layers}
  sample={model.sample} label="Open PRs by year opened" height={AREA_HEIGHT} {width} />
