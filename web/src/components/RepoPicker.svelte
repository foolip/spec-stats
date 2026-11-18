<script lang="ts">
  // All specs or one spec: a native <select>, so picking a spec is one
  // choice (type ahead works, and phones show their own picker). A link
  // with several specs, or all but some (`repos=dom,html`, `repos=-html`),
  // still works and shows as an extra option.
  import type { Repos } from "../lib/url.ts";

  interface Props {
    names: string[];
    standards: string[];
    repos: Repos;
    onchange: (repos: Repos) => void;
  }
  let { names, standards, repos, onchange }: Props = $props();

  const order = $derived(names.map((_, i) => i).sort((a, b) => standards[a].localeCompare(standards[b])));
  const standard = (n: string) => standards[names.indexOf(n)];
  const value = $derived(
    repos.mode === "all" ? "" : repos.mode === "only" && repos.names.length === 1 ? repos.names[0] : "*",
  );
  const otherLabel = $derived(
    repos.mode === "except"
      ? `All but ${repos.names.map(standard).join(", ")}`
      : repos.mode === "only"
        ? repos.names.map(standard).join(", ")
        : "",
  );

  function choose(v: string) {
    if (v === "*") return;
    onchange(v === "" ? { mode: "all" } : { mode: "only", names: [v] });
  }
</script>

<label class="select">
  <span class="menu-label">Spec</span>
  <select {value} onchange={(e) => choose(e.currentTarget.value)}>
    <option value="">All specs</option>
    {#if value === "*"}<option value="*">{otherLabel}</option>{/if}
    <hr />
    {#each order as i (names[i])}
      <option value={names[i]}>{standards[i]}</option>
    {/each}
  </select>
</label>
