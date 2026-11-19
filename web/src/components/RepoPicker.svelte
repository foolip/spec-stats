<script lang="ts">
  // All specs or one spec: a native <select>, so picking a spec is one
  // choice (type-ahead works, and phones show their own picker).
  interface Props {
    names: string[];
    standards: string[];
    /** A repo name, or null for all. */
    repo: string | null;
    onchange: (repo: string | null) => void;
  }
  let { names, standards, repo, onchange }: Props = $props();

  const order = $derived(names.map((_, i) => i).sort((a, b) => standards[a].localeCompare(standards[b])));
</script>

<label class="select">
  <span class="menu-label">Spec</span>
  <select value={repo ?? ""} onchange={(e) => onchange(e.currentTarget.value || null)}>
    <option value="">All specs</option>
    <hr />
    {#each order as i (names[i])}
      <option value={names[i]}>{standards[i]}</option>
    {/each}
  </select>
</label>
