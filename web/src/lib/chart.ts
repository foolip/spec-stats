// Shared by the charts that are shown one above the other, so their time
// axes line up: the same margins at every width.

export interface Margins {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

/** Below this width the area chart has no direct labels at its right edge:
 * they would take a third of a phone's width from the plot, and the legend
 * and tooltip already name the layers and give their values. */
const DIRECT_LABELS_MIN_WIDTH = 480;

export function directLabels(width: number): boolean {
  return width >= DIRECT_LABELS_MIN_WIDTH;
}

/** The right margin holds the area chart's end labels ("112 older") where
 * there are any; otherwise just room for the last x-axis label. */
export function margins(width: number): Margins {
  const right = !directLabels(width) ? 16 : width < 520 ? 100 : 112;
  return { top: 12, right, bottom: 28, left: 40 };
}

/** The charts' heights, fixed, so the page can hold their space before they
 * are drawn (docs/site-design.md, "Loading"). */
export const AREA_HEIGHT = 320;
export const BARS_HEIGHT = 220;
