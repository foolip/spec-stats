const dateFormat = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

/** "17 Nov 2026" for "2026-11-17". */
export function longDate(date: string): string {
  return dateFormat.format(new Date(`${date}T00:00:00Z`));
}

const numberFormat = new Intl.NumberFormat("en-GB");

export function num(n: number): string {
  return numberFormat.format(n);
}

/** "+12", "−3" or "±0", with a real minus sign. */
export function signed(n: number): string {
  if (n === 0) return "±0";
  return n > 0 ? `+${num(n)}` : `−${num(-n)}`;
}
