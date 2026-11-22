<script lang="ts">
  // PRs merged, or issues closed, per period, by time open.
  import BarsPanel from "../components/BarsPanel.svelte";
  import { capitalized } from "../lib/texts.ts";
  import type { IslandProps } from "./index.ts";

  let { model, width }: IslandProps = $props();
  const t = $derived(model.text);
  const w = $derived(model.words);
</script>

<BarsPanel heading="{capitalized(w.items)} {w.done} per {t.unit}, by time open"
  label="{capitalized(w.items)} {w.done} per {t.unit}" summary="Table: {w.doneNoun} per {t.unit}" done={w.done}
  from={model.data.from} start={t.start} end={t.end} bin={t.bin} unitTitle={t.unitTitle}
  periods={model.flowPeriods} counts={model.flowCounts} bands={model.flowBands} {width} />
