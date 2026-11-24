<script lang="ts">
  // PRs merged, by time open, or closed without merging, per period; or
  // issues closed, by time open.
  import BarsPanel from "../components/BarsPanel.svelte";
  import { capitalized } from "../lib/texts.ts";
  import type { IslandProps } from "./index.ts";

  let { model, width }: IslandProps = $props();
  const t = $derived(model.text);
  const w = $derived(model.words);
</script>

<BarsPanel heading="{capitalized(w.items)} {w.flowDone} per {t.unit}, by time open"
  label="{capitalized(w.items)} {w.flowDone} per {t.unit}" summary="Table: {w.flowNoun} per {t.unit}" done={w.flowDone}
  from={model.data.from} start={t.start} end={t.end} bin={t.bin} unitTitle={t.unitTitle}
  periods={model.flowPeriods} counts={model.flowCounts} bands={model.flowBands} onTop={model.flowOnTop} {width} />
