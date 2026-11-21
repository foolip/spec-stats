// Dates and numbers as en-US writes them, by hand rather than with Intl:
// creating an Intl.DateTimeFormat takes tens of milliseconds on a slow
// phone, and the controller formats dates before the first paint
// (docs/site-design.md, "Loading"). By hand, Node (which prerenders) and
// every browser also give exactly the same text.

/** The page's locale, matching `<html lang>` (src/page.ts), for what's
 * still formatted with Intl (bins.ts, in the islands only). */
export const LOCALE = "en-US";

/** Orders strings by UTF-16 code units, for sorting the standards' names.
 * Not localeCompare: its first call sets up a collator, about 20 ms on the
 * throttled phone. For the names in config/db.json the order is the same. */
export function compareText(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

/** en-US's short month names. */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "Nov 17, 2026" for "2026-11-17". */
export function longDate(date: string): string {
  const [y, m, d] = date.split("-");
  return `${MONTHS[Number(m) - 1]} ${Number(d)}, ${y}`;
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
