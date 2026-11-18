<script lang="ts">
  import { PRESETS, fixed, type Context, type Preset, type Range } from "../lib/url.ts";

  interface Props {
    range: Range;
    ctx: Context;
    onchange: (range: Range) => void;
  }
  let { range, ctx, onchange }: Props = $props();

  const LABELS: Record<Preset, string> = { all: "All", "3y": "3 years", "1y": "1 year", "6m": "6 months", "3m": "3 months" };
  const dates = $derived(fixed(range, ctx) as { from: string; to: string });

  function setDate(which: "from" | "to", value: string) {
    if (!value) return;
    const next = { ...dates, [which]: value };
    if (next.from > next.to) return;
    onchange(next);
  }
</script>

<fieldset class="range">
  <legend class="label">Dates</legend>
  <div class="segmented" role="group" aria-label="Date range">
    {#each PRESETS as p (p)}
      <button type="button" aria-pressed={"preset" in range && range.preset === p} onclick={() => onchange({ preset: p })}>
        {LABELS[p]}
      </button>
    {/each}
  </div>
  <label class="date">
    <span class="visually-hidden">From</span>
    <input type="date" min={ctx.from} max={ctx.to} value={dates.from} onchange={(e) => setDate("from", e.currentTarget.value)} />
  </label>
  <span aria-hidden="true">–</span>
  <label class="date">
    <span class="visually-hidden">To</span>
    <input type="date" min={ctx.from} max={ctx.to} value={dates.to} onchange={(e) => setDate("to", e.currentTarget.value)} />
  </label>
</fieldset>
