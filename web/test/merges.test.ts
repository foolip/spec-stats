import assert from "node:assert/strict";
import { test } from "node:test";
import { fromRaw, type RawData } from "../src/lib/data.ts";
import { chooseBin, mergesByPeriod, periodName, periods } from "../src/lib/merges.ts";

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

test("the bin is the smallest period that keeps bars wide enough", () => {
  assert.equal(chooseBin(FROM, 1782 - 365, 1781, 560), "week"); // 53 weeks: 10.6 px
  assert.equal(chooseBin(FROM, 1782 - 365, 1781, 400), "month"); // 7.5 px a week
  assert.equal(chooseBin(FROM, 0, 1781, 560), "month"); // 59 months: 9.5 px
  assert.equal(chooseBin(FROM, 0, 1781, 300), "quarter");
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
  const raw: RawData = {
    meta: { from: FROM, to: "2022-01-31" },
    event_types: types,
    repos: { name: ["html", "dom"], standard: ["HTML", "DOM"] },
    items: { repo: [0, 1, 0, 0], number: [1, 2, 3, 4], created: [0, 0, 0, 0], hours_to_merge: [24, 3, 24.5, 241] },
    events: { day: ev.map((e) => e[0]), item: ev.map((e) => e[1]), event: ev.map((e) => types.indexOf(e[2])) },
  };
  const data = fromRaw(raw);
  const ps = periods(FROM, 0, 30, "week");
  assert.equal(ps[0].first, "2021-12-27");
  assert.deepEqual(mergesByPeriod(data, [0], ps).slice(0, 4), [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]);
  assert.deepEqual(mergesByPeriod(data, [0, 1], ps)[1], [2, 0, 0]);
});
