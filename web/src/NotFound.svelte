<script lang="ts">
  // 404.html: GitHub Pages serves it, with status 404, for every path that
  // isn't a page (src/page.ts). Static: no script and no data.
  import SiteHeader from "./components/SiteHeader.svelte";
  import { VIEW_TEXT } from "./lib/texts.ts";
  import { pagePath, VIEWS } from "./lib/url.ts";

  interface Props {
    root: string;
    icon: string;
  }
  let { root, icon }: Props = $props();
  const href = (view: (typeof VIEWS)[number]) => pagePath({ view, repo: null });
</script>

<SiteHeader {root} {icon} {href} title="WHATWG" />

<main class="wrap">
  <article class="view">
    <hgroup>
      <h2>Page not found</h2>
      <p class="question">There’s no page at this address.</p>
    </hgroup>
    <ul class="not-found">
      {#each VIEWS as v (v)}
        <li><a href="{root}{href(v)}">{VIEW_TEXT[v].title}</a>: {VIEW_TEXT[v].question}</li>
      {/each}
    </ul>
  </article>
</main>

<footer class="site">
  <div class="wrap">
    <p>Not affiliated with the WHATWG. <a href="https://github.com/foolip/spec-stats">Source on GitHub</a>.</p>
  </div>
</footer>
