<script lang="ts">
  // The site's header, on every page: its name, its icon at the top right,
  // and the links to
  // the views. On a view's page, the controller switches views in place
  // when they're clicked.
  import { VIEW_TEXT } from "../lib/texts.ts";
  import { VIEWS, type View } from "../lib/url.ts";

  interface Props {
    /** The site's root on its host, "/spec-stats/". */
    root: string;
    /** The site icon, as a data: URL. */
    icon: string;
    /** Each view's link, from the site's root. */
    href: (view: View) => string;
    /** The view the page shows, if any. */
    current?: View;
  }
  let { root, icon, href, current }: Props = $props();
</script>

<header class="site">
  <div class="wrap masthead">
    <div class="name">
      <a class="brand" href={root}>Living Standard Stats</a>
      <p class="tagline">How the WHATWG’s Living Standards are maintained, from public GitHub data.</p>
    </div>
    <img class="logo" src={icon} alt="" />
  </div>
  <div class="wrap">
    <nav class="views" aria-label="Views">
      {#each VIEWS as v (v)}
        <a href="{root}{href(v)}" data-view={v} aria-current={v === current ? "page" : undefined}>{VIEW_TEXT[v].title}</a>
      {/each}
    </nav>
  </div>
</header>
