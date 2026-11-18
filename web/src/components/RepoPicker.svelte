<script lang="ts">
  import Menu from "./Menu.svelte";
  import { reposFor } from "../lib/repos.ts";
  import { selectedRepos, type Repos } from "../lib/url.ts";

  interface Props {
    names: string[];
    standards: string[];
    repos: Repos;
    onchange: (repos: Repos) => void;
  }
  let { names, standards, repos, onchange }: Props = $props();

  const selected = $derived(new Set(selectedRepos(repos, names).map((i) => names[i])));
  const order = $derived(names.map((_, i) => i).sort((a, b) => standards[a].localeCompare(standards[b])));
  const standard = (n: string) => standards[names.indexOf(n)];
  const summary = $derived(
    repos.mode === "all"
      ? "All"
      : repos.mode === "except"
        ? repos.names.length === 1
          ? `All but ${standard(repos.names[0])}`
          : `All but ${repos.names.length}`
        : repos.names.length <= 2
          ? repos.names.map(standard).join(", ")
          : `${repos.names.length} specs`,
  );

  function toggle(name: string) {
    const next = new Set(selected);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    if (next.size) onchange(reposFor(next, names));
  }
</script>

<Menu label="Specs">
  {#snippet button()}<span class="menu-label">Specs</span> {summary}{/snippet}
  <div class="menu-head">
    <span class="count">{selected.size} of {names.length} specs</span>
    <div class="quick">
      <button type="button" disabled={repos.mode === "all"} onclick={() => onchange({ mode: "all" })}>Select all</button>
      {#if names.includes("html")}
        <button
          type="button"
          disabled={repos.mode === "except" && repos.names.join() === "html"}
          onclick={() => onchange({ mode: "except", names: ["html"] })}>All but HTML</button
        >
      {/if}
    </div>
  </div>
  <ul class="spec-list">
    {#each order as i (names[i])}
      {@const on = selected.has(names[i])}
      <li>
        <label>
          <input
            type="checkbox"
            checked={on}
            disabled={on && selected.size === 1}
            title={on && selected.size === 1 ? "At least one spec stays selected" : undefined}
            onchange={() => toggle(names[i])}
          />
          {standards[i]}
        </label>
        <button
          type="button"
          class="only"
          aria-label="Only {standards[i]}"
          onclick={() => onchange({ mode: "only", names: [names[i]] })}>only</button
        >
      </li>
    {/each}
  </ul>
</Menu>
