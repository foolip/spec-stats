<script lang="ts">
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
  const summary = $derived(
    repos.mode === "all"
      ? "All specs"
      : repos.mode === "except"
        ? `All but ${repos.names.map((n) => standards[names.indexOf(n)]).join(", ")}`
        : repos.names.length <= 3
          ? repos.names.map((n) => standards[names.indexOf(n)]).join(", ")
          : `${repos.names.length} specs`,
  );

  let details: HTMLDetailsElement;

  // Close on a click outside, or Escape.
  $effect(() => {
    const onClick = (e: MouseEvent) => {
      if (details.open && !details.contains(e.target as Node)) details.open = false;
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && details.open) {
        details.open = false;
        details.querySelector("summary")?.focus();
      }
    };
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", onClick);
      document.removeEventListener("keydown", onKey);
    };
  });

  function toggle(name: string) {
    const next = new Set(selected);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    onchange(reposFor(next, names));
  }
</script>

<details class="picker" bind:this={details}>
  <summary><span class="label">Specs</span> {summary}</summary>
  <div class="popover">
    <div class="quick">
      <button type="button" aria-pressed={repos.mode === "all"} onclick={() => onchange({ mode: "all" })}>All</button>
      {#if names.includes("html")}
        <button
          type="button"
          aria-pressed={repos.mode === "except" && repos.names.join() === "html"}
          onclick={() => onchange({ mode: "except", names: ["html"] })}>All but HTML</button
        >
      {/if}
    </div>
    <ul>
      {#each order as i (names[i])}
        <li>
          <label>
            <input type="checkbox" checked={selected.has(names[i])} onchange={() => toggle(names[i])} />
            {standards[i]}
            <span class="repo">{names[i]}</span>
          </label>
        </li>
      {/each}
    </ul>
  </div>
</details>
