<script lang="ts">
  // A whole page of the open PRs view, rendered on the server only
  // (src/page.ts): everything but the charts' drawings, with the values for
  // the state the page is for. In the browser, the controller
  // (src/controller.ts) runs the URL and the controls, and main.ts mounts
  // the islands (src/islands/), one per section, once the data has loaded.
  import Controls from "./components/Controls.svelte";
  import { islands } from "./islands/index.ts";
  import { longDate } from "./lib/format.ts";
  import type { Model } from "./lib/model.svelte.ts";

  interface Props {
    model: Model;
    /** The site's root on its host, "/spec-stats/". */
    root: string;
    /** The site icon, public/favicon.svg, as a data: URL, so it's in the
     * first paint. */
    icon: string;
    /** The controller's <script>, which runs before the footer is parsed:
     * the page's <link rel="expect" href="#footer" blocking="render">
     * holds the first paint until then. */
    controller: string;
  }
  let { model, root, icon, controller }: Props = $props();
  const t = $derived(model.text);
</script>

<header class="site">
  <div class="wrap">
    <a class="brand" href={root}><img class="logo" src={icon} alt="" />spec-stats</a>
    <p class="tagline">How the WHATWG’s Living Standards are maintained, from public GitHub data.</p>
  </div>
</header>

<main class="wrap">
  <p class="notice" role="alert" data-error hidden></p>
  <article class="view">
    <hgroup>
      <h1>Reviews</h1>
      <p class="question">How many PRs are open, and how many are getting merged?</p>
    </hgroup>

    <Controls state={model.view} text={t} ctx={model.ctx} standards={model.data.repos.standard} />

    <div data-island="summary"><islands.summary {model} /></div>
    <div data-island="openPanel"><islands.openPanel {model} /></div>
    <div data-island="mergesPanel"><islands.mergesPanel {model} /></div>
    <div data-island="bySpec"><islands.bySpec {model} /></div>
  </article>
</main>

{@html controller}

<footer class="site" id="footer">
  <div class="wrap">
    <p>Data from {longDate(model.data.from)} to {longDate(model.data.to)}, from the GitHub REST API.</p>
    <p>Not affiliated with the WHATWG. <a href="https://github.com/foolip/spec-stats">Source on GitHub</a>.</p>
  </div>
</footer>
