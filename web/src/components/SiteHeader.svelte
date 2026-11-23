<script lang="ts">
  // The site's header, on every page, laid out as the WHATWG's standards'
  // headers are: the title (the spec, or "WHATWG" for all specs), "Living
  // Statistics — Last Updated", the icon at the top right, and then the
  // links to the views. On a view's page, the controller sets the title
  // as the spec changes, and switches views in place when they're clicked.
  import { specDate } from "../lib/format.ts";
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
    /** The title: "DOM", "WHATWG". */
    title: string;
    /** The data's last day, "2026-11-21", if the page has data. */
    updated?: string;
  }
  let { root, icon, href, current, title, updated }: Props = $props();
</script>

<header class="site">
  <div class="wrap masthead">
    <hgroup>
      <h1 data-control="title">{title}</h1>
      <p class="subtitle">Living Statistics{updated ? ` — Last Updated ${specDate(updated)}` : ""}</p>
    </hgroup>
    <a class="logo" href={root}><img src={icon} alt="Living Statistics" /></a>
  </div>
  <div class="wrap">
    <nav class="views" aria-label="Views">
      {#each VIEWS as v (v)}
        <a href="{root}{href(v)}" data-view={v} aria-current={v === current ? "page" : undefined}>{VIEW_TEXT[v].title}</a>
      {/each}
    </nav>
  </div>
</header>
