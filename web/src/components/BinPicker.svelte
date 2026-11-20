<script lang="ts">
  // The bars' period: a native <select>, like the spec picker. "Auto" names
  // the period it chose.
  import type { Bin } from "../lib/bins.ts";
  import { BIN_CHOICES, type BinChoice } from "../lib/url.ts";

  interface Props {
    bin: BinChoice;
    /** What "auto" resolves to now. */
    auto: Bin;
    onchange: (bin: BinChoice) => void;
  }
  let { bin, auto, onchange }: Props = $props();

  const LABELS: Record<Bin, string> = { day: "Day", week: "Week", month: "Month", quarter: "Quarter" };
</script>

<label class="select">
  <span class="menu-label">Per</span>
  <select value={bin} onchange={(e) => onchange(e.currentTarget.value as BinChoice)}>
    {#each BIN_CHOICES as b (b)}
      <option value={b}>{b === "auto" ? `Auto (${LABELS[auto].toLowerCase()})` : LABELS[b]}</option>
    {/each}
  </select>
</label>
