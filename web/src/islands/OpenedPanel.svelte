<script lang="ts">
  // PRs or issues opened per period, by how soon they were closed.
  import BarsPanel from "../components/BarsPanel.svelte";
  import { capitalized } from "../lib/texts.ts";
  import type { IslandProps } from "./index.ts";

  let { model, width }: IslandProps = $props();
  const t = $derived(model.text);
  const w = $derived(model.words);
</script>

<BarsPanel heading="{capitalized(w.items)} opened per {t.unit}, by time to close"
  label="{capitalized(w.items)} opened per {t.unit}" summary="Table: {w.items} opened per {t.unit}" done="opened"
  from={model.data.from} start={t.start} end={t.end} bin={t.bin} unitTitle={t.unitTitle}
  periods={model.opened.periods} counts={model.opened.counts} bands={model.openedBands} {width} />
