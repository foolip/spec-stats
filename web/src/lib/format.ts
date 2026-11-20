// Dates and numbers as en-GB writes them, by hand rather than with Intl:
// creating an Intl.DateTimeFormat takes tens of milliseconds on a slow
// phone, and the controller formats dates before the first paint
// (docs/site-design.md, "Loading"). By hand, Node (which prerenders) and
// every browser also give exactly the same text.

/** en-GB's short month names, "Sept" included. */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sept", "Oct", "Nov", "Dec"];

/** "17 Nov 2026" for "2026-11-17". */
export function longDate(date: string): string {
  const [y, m, d] = date.split("-");
  return `${Number(d)} ${MONTHS[Number(m) - 1]} ${y}`;
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
