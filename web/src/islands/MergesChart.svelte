<script lang="ts">
  // PRs merged per period, drawn into its box once the data has loaded.
  import StackedBars from "../components/StackedBars.svelte";
  import { periodName } from "../lib/bins.ts";
  import { BARS_HEIGHT } from "../lib/chart.ts";
  import type { IslandProps } from "./index.ts";

  let { model, width }: IslandProps = $props();
</script>

<StackedBars from={model.data.from} start={model.text.start} end={model.text.end} periods={model.mergePeriods}
  name={(p) => periodName(p, model.text.bin)} layers={model.mergeLayers} label="PRs merged per {model.text.unit}"
  height={BARS_HEIGHT} {width} />
