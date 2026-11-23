// Dates and numbers as en-US writes them, by hand rather than with Intl or
// d3-time-format: Intl's first use takes tens of milliseconds on a slow
// phone, and the controller bundles this file (through stateText() in
// texts.ts), where d3-time-format would add about 11 KB to every page's
// inline script (docs/site-design.md, "Loading"). By hand, Node (which
// prerenders) and every browser also give exactly the same text.

/** The page's locale, for `<html lang>` (src/page.ts). */
export const LOCALE = "en-US";

/** en-US's short month names. */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "Nov 17, 2026" for "2026-11-17". */
export function longDate(date: string): string {
  const [y, m, d] = date.split("-");
  return `${MONTHS[Number(m) - 1]} ${Number(d)}, ${y}`;
}

/** en-US's month names, in full. */
const FULL_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/** "17 November 2026" for "2026-11-17": day first, as the WHATWG's
 * standards write "Last Updated". */
export function specDate(date: string): string {
  const [y, m, d] = date.split("-");
  return `${Number(d)} ${FULL_MONTHS[Number(m) - 1]} ${y}`;
}

/** "1,234" */
export function num(n: number): string {
  const [int, frac] = String(Math.abs(n)).split(".");
  const grouped = int.replace(/\B(?=(\d{3})+$)/g, ",");
  return `${n < 0 ? "-" : ""}${grouped}${frac === undefined ? "" : `.${frac}`}`;
}

/** "+12", "−3" or "±0", with a real minus sign. */
export function signed(n: number): string {
  if (n === 0) return "±0";
  return n > 0 ? `+${num(n)}` : `−${num(-n)}`;
}
