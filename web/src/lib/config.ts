// What a prerendered page tells its controller (src/controller.ts), in a
// <script type="application/json" id="config"> element.

import type { View } from "./url.ts";

export interface PageConfig {
  /** The site's root on its host: "/spec-stats/". */
  root: string;
  /** The data file, from the site's root. */
  data: string;
  /** The window, YYYY-MM-DD. */
  from: string;
  to: string;
  /** Every repo's name. */
  repos: string[];
  /** Every repo's standard's name, for the page title. */
  standards: string[];
  /** The view the page shows. */
  view: View;
  /** The URL, relative to the site's root, the page was prerendered for:
   * its values are right for that URL only. */
  prerendered: string;
}
