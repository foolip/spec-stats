import assert from "node:assert/strict";
import { test } from "node:test";
import { longDate, num, signed } from "../src/lib/format.ts";

test("dates and numbers are written as Intl's en-GB writes them", () => {
  const dates = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  for (let m = 1; m <= 12; m++) {
    for (const d of [1, 9, 10, 28]) {
      const date = `2026-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      assert.equal(longDate(date), dates.format(new Date(`${date}T00:00:00Z`)));
    }
  }
  const numbers = new Intl.NumberFormat("en-GB");
  for (const n of [0, 7, 42, 999, 1000, 1234, 12345, 123456, 1234567, -1234, 2.5, 1234.5]) assert.equal(num(n), numbers.format(n));
  assert.equal(signed(1234), "+1,234");
  assert.equal(signed(-3), "−3");
  assert.equal(signed(0), "±0");
});
