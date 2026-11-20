<script lang="ts">
  // A whole page of the open PRs view, rendered on the server only
  // (src/page.ts): everything but the charts' drawings, with the values for
  // the state the page is for. In the browser, the controller
  // (src/controller.ts) runs the controls, the texts marked data-text and
  // the by-spec table's visibility, and main.ts mounts the islands
  // (src/islands/) once the data has loaded.
  import Controls from "./components/Controls.svelte";
  import { islands } from "./islands/index.ts";
  import { AREA_HEIGHT, BARS_HEIGHT } from "./lib/chart.ts";
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

    <section class="tiles" aria-label="Summary">
      <div class="tile">
        <div class="tile-label">Open on <span data-text="end">{t.endDate}</span></div>
        <div data-island="openNow"><islands.openNow {model} /></div>
      </div>
      <div class="tile">
        <div class="tile-label">Change since <span data-text="start">{t.startDate}</span></div>
        <div data-island="openChange"><islands.openChange {model} /></div>
      </div>
      <div class="tile">
        <div class="tile-label">Merged since <span data-text="start">{t.startDate}</span></div>
        <div data-island="merged"><islands.merged {model} /></div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <h2>Open PRs at the end of each <span data-text="unit">{t.unit}</span>, by year opened</h2>
        <ul class="legend">
          {#each [...model.layers].reverse() as l (l.label)}
            <li><span class="swatch" style:background={l.color}></span>{l.label}</li>
          {/each}
        </ul>
      </div>
      <div class="chart-box" data-island="openChart" style:height="{AREA_HEIGHT}px"></div>
      <details class="table-view">
        <summary>Table: month ends</summary>
        <table>
          <thead>
            <tr>
              <th scope="col">Date</th>
              {#each [...model.layers].reverse() as l (l.label)}<th scope="col">{l.label}</th>{/each}
              <th scope="col">Open</th>
            </tr>
          </thead>
          <tbody data-island="openRows"><islands.openRows {model} /></tbody>
        </table>
      </details>
    </section>

    <section class="panel">
      <div class="panel-head">
        <h2>PRs merged per <span data-text="unit">{t.unit}</span>, by time open</h2>
        <ul class="legend">
          {#each model.mergeBands as l (l.label)}
            <li><span class="swatch" style:background={l.color}></span>{l.label}</li>
          {/each}
        </ul>
      </div>
      <div class="chart-box" data-island="mergesChart" style:height="{BARS_HEIGHT}px"></div>
      <details class="table-view">
        <summary>Table: merges per <span data-text="unit">{t.unit}</span></summary>
        <table>
          <thead>
            <tr>
              <th scope="col" data-text="unit-title">{t.unitTitle}</th>
              {#each model.mergeBands as l (l.label)}<th scope="col">{l.label}</th>{/each}
              <th scope="col">Merged</th>
            </tr>
          </thead>
          <tbody data-island="mergesRows"><islands.mergesRows {model} /></tbody>
        </table>
      </details>
    </section>

    <!-- For all specs only: with one, it would only repeat the tiles. The
         controller shows and hides it. -->
    <section class="panel" id="by-spec" hidden={model.view.repo !== null}>
      <h2>By spec</h2>
      <table class="by-spec">
        <thead>
          <tr>
            <th scope="col">Spec</th>
            <th scope="col" class="n">Open</th>
            <th scope="col" class="n">Change</th>
            <th scope="col" class="bar-col"><span class="visually-hidden">Open, as a bar</span></th>
          </tr>
        </thead>
        <tbody data-island="bySpecRows"><islands.bySpecRows {model} /></tbody>
      </table>
    </section>
  </article>
</main>

{@html controller}

<footer class="site" id="footer">
  <div class="wrap">
    <p>Data from {longDate(model.data.from)} to {longDate(model.data.to)}, from the GitHub REST API.</p>
    <p>Not affiliated with the WHATWG. <a href="https://github.com/foolip/spec-stats">Source on GitHub</a>.</p>
  </div>
</footer>
