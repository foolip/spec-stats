import assert from "node:assert/strict";
import { test } from "node:test";
import { fromRaw } from "../src/lib/data.ts";
import { encode, shuffled, type Table } from "./helpers.ts";
import { chooseBin, periodName, periods, sampleDays } from "../src/lib/bins.ts";
import { mergesByPeriod } from "../src/lib/merges.ts";

const FROM = "2022-01-01";

test("periods are ISO weeks, months or quarters, clipped to the range", () => {
  // 2026-11-18 is a Wednesday; 2026-11-17 a Tuesday.
  const start = 1782 - 365; // 2025-11-18, a Tuesday
  const weeks = periods(FROM, start, 1781, "week");
  assert.equal(weeks.length, 53);
  assert.deepEqual(weeks[0], { start, end: start + 5, first: "2025-11-17", partial: true });
  assert.equal(periodName(weeks[0], "week"), "2025-W47");
  assert.deepEqual(weeks.at(-1), { start: 1780, end: 1781, first: "2026-11-16", partial: true });
  assert.equal(periodName(weeks.at(-1)!, "week"), "2026-W47");
  assert.ok(weeks.slice(1, -1).every((w) => !w.partial && w.end - w.start === 6));
  // ISO weeks at a year boundary: 2026-12-28 is in 2026-W53, 2021-01-03 in 2020-W53.
  assert.equal(periodName({ start: 0, end: 0, first: "2026-12-28", partial: false }, "week"), "2026-W53");
  assert.equal(periodName({ start: 0, end: 0, first: "2020-12-28", partial: false }, "week"), "2020-W53");
  const months = periods(FROM, 0, 1781, "month");
  assert.equal(months.length, 59);
  assert.deepEqual(months[0], { start: 0, end: 30, first: "2022-01-01", partial: false });
  assert.equal(periodName(months.at(-1)!, "month"), "November 2026");
  assert.ok(months.at(-1)!.partial);
  const quarters = periods(FROM, 0, 1781, "quarter");
  assert.equal(quarters.length, 20);
  assert.equal(periodName(quarters.at(-1)!, "quarter"), "2026 Q4");
});

test("days are whole periods, never partial", () => {
  const days = periods(FROM, 10, 16, "day");
  assert.equal(days.length, 7);
  assert.ok(days.every((p, k) => p.start === 10 + k && p.end === p.start && !p.partial));
  assert.equal(periodName(days[0], "day"), "Tue, Jan 11, 2022");
});

test("a count is drawn on the range's first day and each period's last", () => {
  // 2022-01-03 is a Monday: days 2–8 are the first whole ISO week.
  const weeks = periods(FROM, 0, 20, "week");
  assert.deepEqual(sampleDays(weeks), [0, 1, 8, 15, 20]);
  // A range starting on a Sunday: its first day is also its first week's last.
  assert.deepEqual(sampleDays(periods(FROM, 1, 8, "week")), [1, 8]);
  assert.deepEqual(sampleDays(periods(FROM, 3, 6, "day")), [3, 4, 5, 6]);
  assert.deepEqual(sampleDays([]), []);
});

test("auto is the smallest period with at most 54 bars", () => {
  // From the range alone: the smallest period with at most 54 bars.
  assert.equal(chooseBin(FROM, 1782 - 365, 1781), "week"); // a year: 53 weeks
  assert.equal(chooseBin(FROM, 1782 - 371, 1781), "week"); // 54 weeks
  assert.equal(chooseBin(FROM, 1782 - 378, 1781), "month"); // 55 weeks: 13 months
  assert.equal(chooseBin(FROM, 1782 - 1095, 1781), "month"); // three years: 37 months
  assert.equal(chooseBin(FROM, 0, 1781), "quarter"); // 59 months: 20 quarters
  // Auto never chooses days, however short: a day's merges are mostly 0 to 3.
  assert.equal(chooseBin(FROM, 1690, 1781), "week");
});

test("merges are counted per period and by time to merge", () => {
  const types = ["_created", "closed", "merged"];
  const ev: [number, number, string][] = [
    [0, 0, "_created"], [0, 1, "_created"], [0, 2, "_created"], [0, 3, "_created"],
    [2, 0, "closed"], [2, 0, "merged"],   // week 1 (2022-01-03 is a Monday): within a day
    [3, 1, "closed"], [3, 1, "merged"],   // week 1, other repo: left out
    [10, 2, "closed"], [10, 2, "merged"], // week 2: 1–10 days
    [17, 3, "closed"], [17, 3, "merged"], // week 3: over 10 days
  ];
  const table: Table = {
    meta: { from: FROM, to: "2022-01-31" },
    event_types: types,
    repos: { name: ["html", "dom"], standard: ["HTML", "DOM"] },
    items: { repo: [0, 1, 0, 0], number: [1, 2, 3, 4], created: [0, 0, 0, 0], hours_to_merge: [24, 3, 24.5, 241] },
    events: ev,
  };
  const ps = periods(FROM, 0, 30, "week");
  assert.equal(ps[0].first, "2021-12-27");
  // The order of items and events makes no difference.
  for (const data of [fromRaw(encode(table)), fromRaw(encode(shuffled(table)))]) {
    assert.deepEqual(mergesByPeriod(data, [0], ps).slice(0, 4), [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]);
    assert.deepEqual(mergesByPeriod(data, [0, 1], ps)[1], [2, 0, 0]);
    // Only days in the periods count: the merge on day 17 is left out.
    assert.deepEqual(mergesByPeriod(data, [0], periods(FROM, 0, 16, "week")).flat().reduce((a, b) => a + b), 2);
  }
});
