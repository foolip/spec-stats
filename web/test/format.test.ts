import assert from "node:assert/strict";
import { test } from "node:test";
import { LOCALE, longDate, num, signed, specDate } from "../src/lib/format.ts";

test("dates and numbers are written as Intl writes them in the page's locale", () => {
  const dates = new Intl.DateTimeFormat(LOCALE, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  for (let m = 1; m <= 12; m++) {
    for (const d of [1, 9, 10, 28]) {
      const date = `2026-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      assert.equal(longDate(date), dates.format(new Date(`${date}T00:00:00Z`)));
    }
  }
  const numbers = new Intl.NumberFormat(LOCALE);
  for (const n of [0, 7, 42, 999, 1000, 1234, 12345, 123456, 1234567, -1234, 2.5, 1234.5]) assert.equal(num(n), numbers.format(n));
  assert.equal(signed(1234), "+1,234");
  assert.equal(signed(-3), "−3");
  assert.equal(signed(0), "±0");
});

test("the last updated date is written as the WHATWG's standards write it", () => {
  assert.equal(specDate("2026-11-15"), "15 November 2026");
  assert.equal(specDate("2026-01-01"), "1 January 2026");
  const dates = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
  for (let m = 1; m <= 12; m++) {
    const date = `2026-${String(m).padStart(2, "0")}-09`;
    assert.equal(specDate(date), dates.format(new Date(`${date}T00:00:00Z`)));
  }
});
