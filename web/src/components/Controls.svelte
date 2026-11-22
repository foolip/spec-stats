<script lang="ts">
  // The filter bar, rendered on the server only: plain HTML that the
  // controller (src/controller.ts) finds by its data-control attributes
  // and runs, from before the first paint. One row of same-sized controls:
  // the spec as a native <select> (type-ahead works, and phones show their
  // own picker), the date range as presets, the bars' period as a
  // <select>, and "Copy link".
  import { BIN_LABELS, PRESET_LABELS, PRESET_TITLES, type StateText } from "../lib/texts.ts";
  import { BIN_CHOICES, PRESETS, type Context, type State } from "../lib/url.ts";

  interface Props {
    state: State;
    text: StateText;
    ctx: Context;
    standards: string[];
  }
  let { state, text, ctx, standards }: Props = $props();

  // In the order the build lists them (spec_order in specstats/build.py).
  const names = $derived(ctx.repoNames);
</script>

<div class="controls" role="group" aria-label="Filters">
  <label class="select">
    <span class="menu-label">Spec</span>
    <select data-control="repo">
      <option value="" selected={state.repo === null}>All specs</option>
      <hr />
      {#each names as name, i (name)}
        <option value={name} selected={state.repo === name}>{standards[i]}</option>
      {/each}
    </select>
  </label>

  <div class="segmented" role="group" aria-label="Date range">
    {#each PRESETS as p (p)}
      <button type="button" title={PRESET_TITLES[p]} aria-label={PRESET_TITLES[p]} data-preset={p}
        aria-pressed={"preset" in state.range && state.range.preset === p}>{PRESET_LABELS[p]}</button>
    {/each}
  </div>

  <label class="select">
    <span class="menu-label">Per</span>
    <select data-control="bin">
      {#each BIN_CHOICES as b (b)}
        <option value={b} selected={state.bin === b}>{b === "auto" ? text.autoLabel : BIN_LABELS[b]}</option>
      {/each}
    </select>
  </label>

  <!-- Both labels share one grid cell, so the width never changes. -->
  <button type="button" class="copy" title="Copy a link to this view, with its dates fixed" data-control="copy">
    <span>Copy link</span>
    <span class="hidden" aria-hidden="true">Link copied</span>
  </button>
  <span class="visually-hidden" role="status" data-control="status"></span>
</div>
