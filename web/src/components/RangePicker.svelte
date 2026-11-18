<script lang="ts">
  import Menu from "./Menu.svelte";
  import { longDate } from "../lib/format.ts";
  import { PRESETS, fixed, type Context, type Preset, type Range } from "../lib/url.ts";

  interface Props {
    range: Range;
    ctx: Context;
    onchange: (range: Range) => void;
  }
  let { range, ctx, onchange }: Props = $props();

  const LABELS: Record<Preset, string> = { all: "All", "3y": "3 yrs", "1y": "1 yr", "6m": "6 mo", "3m": "3 mo" };
  const TITLES: Record<Preset, string> = { all: "All", "3y": "3 years", "1y": "1 year", "6m": "6 months", "3m": "3 months" };
  const dates = $derived(fixed(range, ctx) as { from: string; to: string });
  const custom = $derived("from" in range);

  function setDate(which: "from" | "to", value: string) {
    if (!value) return;
    const next = { ...dates, [which]: value };
    if (next.from > next.to) return;
    onchange(next);
  }
</script>

<div class="segmented" role="group" aria-label="Date range">
  {#each PRESETS as p (p)}
    <button
      type="button"
      title={TITLES[p]}
      aria-label={TITLES[p]}
      aria-pressed={"preset" in range && range.preset === p}
      onclick={() => onchange({ preset: p })}>{LABELS[p]}</button
    >
  {/each}
  <Menu label="Custom dates" buttonClass="segment-menu" pressed={custom}>
    {#snippet button()}{custom ? `${longDate(dates.from)} – ${longDate(dates.to)}` : "Custom"}{/snippet}
    <div class="dates">
      <label>
        From
        <input type="date" min={ctx.from} max={dates.to} value={dates.from}
          onchange={(e) => setDate("from", e.currentTarget.value)} />
      </label>
      <label>
        To
        <input type="date" min={dates.from} max={ctx.to} value={dates.to}
          onchange={(e) => setDate("to", e.currentTarget.value)} />
      </label>
    </div>
    <p class="menu-note">Data runs from {longDate(ctx.from)} to {longDate(ctx.to)}.</p>
  </Menu>
</div>
