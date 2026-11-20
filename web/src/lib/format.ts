/** The page's locale, matching `<html lang>` in index.html. */
export const LOCALE = "en-US";

const dateFormat = new Intl.DateTimeFormat(LOCALE, {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

/** "Nov 17, 2026" for "2026-11-17". */
export function longDate(date: string): string {
  return dateFormat.format(new Date(`${date}T00:00:00Z`));
}

const numberFormat = new Intl.NumberFormat(LOCALE);

export function num(n: number): string {
  return numberFormat.format(n);
}

/** "+12", "−3" or "±0", with a real minus sign. */
export function signed(n: number): string {
  if (n === 0) return "±0";
  return n > 0 ? `+${num(n)}` : `−${num(-n)}`;
}
