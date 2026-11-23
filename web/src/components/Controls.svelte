<script lang="ts">
  // The filter bar, rendered on the server only: plain HTML that the
  // controller (src/controller.ts) finds by its data-control attributes
  // and runs, from before the first paint. One row of same-sized controls:
  // the spec as a native <select> (type-ahead works, and phones show their
  // own picker), and the date range and the bars' period as <select>s too.
  import { BIN_LABELS, CUSTOM_LABEL, PRESET_LABELS, type StateText } from "../lib/texts.ts";
  import { BIN_CHOICES, PRESETS, rangePreset, type Context, type State } from "../lib/url.ts";

  interface Props {
    state: State;
    text: StateText;
    ctx: Context;
    standards: string[];
  }
  let { state, text, ctx, standards }: Props = $props();

  // In the order the build lists them (spec_order in specstats/build.py).
  const names = $derived(ctx.repoNames);
  // Null for dates that are no choice's, shown as an extra option.
  const preset = $derived(rangePreset(state.range, ctx));
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

  <label class="select">
    <span class="menu-label">Period</span>
    <select data-control="range">
      {#each PRESETS as p (p)}
        <option value={p} selected={preset === p}>{PRESET_LABELS[p]}</option>
      {/each}
      {#if preset === null}
        <option value="" selected>{CUSTOM_LABEL}</option>
      {/if}
    </select>
  </label>

  <label class="select">
    <span class="menu-label">Per</span>
    <select data-control="bin">
      {#each BIN_CHOICES as b (b)}
        <option value={b} selected={state.bin === b}>{b === "auto" ? text.autoLabel : BIN_LABELS[b]}</option>
      {/each}
    </select>
  </label>
</div>
