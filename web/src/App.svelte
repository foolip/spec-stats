<script lang="ts">
  import { load, type Data } from "./lib/data.ts";
  import { longDate } from "./lib/format.ts";
  import { parse, serialize, type Context, type State } from "./lib/url.ts";
  import OpenPrs from "./views/OpenPrs.svelte";

  let data = $state<Data | null>(null);
  let error = $state<string | null>(null);
  let view = $state<State | null>(null);

  function context(d: Data): Context {
    return { repoNames: d.repos.name, from: d.from, to: d.to };
  }

  /** Read the view from the URL, and rewrite the URL without anything it
   * didn't understand. */
  function readUrl(d: Data) {
    view = parse(location.search, context(d));
    const search = serialize(view);
    if (search !== location.search) history.replaceState(null, "", location.pathname + search + location.hash);
  }

  /** Change the view: a new history entry for a new view, the same entry
   * for a control on the same view. */
  function navigate(next: State) {
    if (!view) return;
    const push = next.view !== view.view;
    view = next;
    const url = location.pathname + serialize(next) + location.hash;
    if (push) history.pushState(null, "", url);
    else history.replaceState(null, "", url);
  }

  load()
    .then((d) => {
      data = d;
      readUrl(d);
    })
    .catch((e: unknown) => (error = String(e)));

  $effect(() => {
    const onPop = () => data && readUrl(data);
    addEventListener("popstate", onPop);
    return () => removeEventListener("popstate", onPop);
  });
</script>

<header class="site">
  <div class="wrap">
    <a class="brand" href="./"
      ><img class="logo" src="favicon.svg" alt="" />spec-stats</a
    >
    <p class="tagline">How the WHATWG’s Living Standards are maintained, from public GitHub data.</p>
  </div>
</header>

<main class="wrap">
  {#if error}
    <p class="notice" role="alert">Couldn’t load the data: {error}</p>
  {:else if !data || !view}
    <p class="notice" aria-live="polite">Loading…</p>
  {:else if view.view === "open-prs"}
    <OpenPrs {data} state={view} {navigate} ctx={context(data)} />
  {/if}
</main>

<footer class="site">
  <div class="wrap">
    {#if data}
      <p>Data from {longDate(data.from)} to {longDate(data.to)}, from the GitHub REST API.</p>
    {/if}
    <p>Not affiliated with the WHATWG. <a href="https://github.com/foolip/spec-stats">Source on GitHub</a>.</p>
  </div>
</footer>
