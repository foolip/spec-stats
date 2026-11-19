// Shared by the charts that are shown one above the other, so their time
// axes line up: the same margins at every width.

export interface Margins {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

/** The right margin holds the area chart's end labels ("112 before 2022"). */
export function margins(width: number): Margins {
  return { top: 12, right: width < 520 ? 100 : 112, bottom: 28, left: 40 };
}
