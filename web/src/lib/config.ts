// What a prerendered page tells its controller (src/controller.ts), in a
// <script type="application/json" id="config"> element.

export interface PageConfig {
  /** The data file, relative to the site's root (the page's <base>). */
  data: string;
  /** The window, YYYY-MM-DD. */
  from: string;
  to: string;
  /** Every repo's name. */
  repos: string[];
  /** Every repo's standard's name, for the page title. */
  standards: string[];
  /** The URL, relative to the site's root, the page was prerendered for:
   * its values are right for that URL only. */
  prerendered: string;
}
