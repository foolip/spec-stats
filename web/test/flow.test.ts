import assert from "node:assert/strict";
import { test } from "node:test";
import { periodNote, periods } from "../src/lib/bins.ts";
import { fromRaw } from "../src/lib/data.ts";
import { closes, flowByPeriod, merges, openedByPeriod, unmergedCloses } from "../src/lib/flow.ts";
import { encode, shuffled, type Table } from "./helpers.ts";

const FROM = "2022-01-01";

test("merges are counted per period and by time to merge, and closes without merging apart", () => {
  const table: Table = {
    meta: { from: FROM, to: "2022-01-31" },
    repos: { name: ["html", "dom"], standard: ["HTML", "DOM"] },
    items: {
      repo: [0, 1, 0, 0, 0, 0],
      number: [1, 2, 3, 4, 5, 6],
      kind: [2, 2, 2, 2, 2, 1],
      created: [1, 2, 1, 0, 0, 0],
      // Week 1 (2022-01-03 is a Monday, day 2): within a day; in the other
      // repo, the same. Week 2: 9 days, and exactly 10. Week 3: over 10
      // days. #6, closed without merging in week 1.
      closed: [2, 3, 10, 10, 17, 4],
      later_in_day: [0, 0, 0, 0, 0, 0],
    },
  };
  const ps = periods(FROM, 0, 30, "week");
  assert.equal(ps[0].first, "2021-12-27");
  // The order of items makes no difference.
  for (const data of [fromRaw(encode(table)), fromRaw(encode(shuffled(table)))]) {
    const flow = merges(data);
    assert.deepEqual(flowByPeriod(data, flow, [0], ps).slice(0, 4), [[0, 0, 0], [1, 0, 0], [0, 2, 0], [0, 0, 1]]);
    assert.deepEqual(flowByPeriod(data, flow, [0, 1], ps)[1], [2, 0, 0]);
    // Only days in the periods count: the merge on day 17 is left out.
    assert.deepEqual(flowByPeriod(data, flow, [0], periods(FROM, 0, 16, "week")).flat().reduce((a, b) => a + b), 3);
    // Without bands, one count per period.
    assert.deepEqual(flowByPeriod(data, unmergedCloses(data), [0, 1], ps).slice(0, 3), [[0], [1], [0]]);
  }
});

test("issues are counted at their last close, by time open", () => {
  const table: Table = {
    meta: { from: FROM, to: "2022-01-31" },
    repos: { name: ["html"], standard: ["HTML"] },
    items: {
      repo: [0, 0, 0, 0, 0, 0],
      number: [1, 2, 3, 4, 5, 6],
      kind: [0, 0, 0, 0, 2, 0],
      // #1 week 1, within a week. #2 week 2, 30 days. #3 open (closed and
      // reopened). #4 week 3, over 90 days. #5 a PR: not counted. #6 week 2,
      // exactly 7 days.
      created: [0, -20, 0, -200, 0, 3],
      closed: [2, 10, null, 17, 9, 10],
    },
  };
  const ps = periods(FROM, 0, 30, "week");
  for (const data of [fromRaw(encode(table)), fromRaw(encode(shuffled(table)))]) {
    assert.deepEqual(flowByPeriod(data, closes(data), [0], ps).slice(0, 4), [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 0, 1]]);
    assert.deepEqual(flowByPeriod(data, merges(data), [0], ps).slice(0, 4), [[0, 0, 0], [0, 0, 0], [0, 1, 0], [0, 0, 0]]);
  }
});

test("items opened are counted per period, by time to close", () => {
  const table: Table = {
    meta: { from: FROM, to: "2022-01-31" },
    repos: { name: ["html"], standard: ["HTML"] },
    items: {
      repo: [0, 0, 0, 0, 0, 0, 0, 0],
      number: [1, 2, 3, 4, 5, 6, 7, 8],
      kind: [0, 0, 0, 0, 0, 0, 2, 0],
      // Week 1: #1 within 1 day; #2 5 days; #3 still open; #4 7 days and a
      // bit (closed later). Week 2: #5 20 days. #6, opened before the
      // window: not counted. #7, a PR: counted only for PRs. #8, week 4, in
      // the last 7 days.
      created: [2, 3, 4, 3, 10, -40, 10, 24],
      closed: [2, 8, null, 10, 30, 11, 10, null],
      later_in_day: [1, 0, 0, 1, 0, 0, 0, 0],
    },
  };
  const ps = periods(FROM, 0, 30, "week");
  for (const data of [fromRaw(encode(table)), fromRaw(encode(shuffled(table)))]) {
    const issues = openedByPeriod(data, "issue", [0], ps);
    assert.deepEqual(issues.counts.slice(0, 5), [[0, 0, 0], [2, 1, 1], [0, 1, 0], [0, 0, 0], [0, 0, 1]]);
    assert.deepEqual(openedByPeriod(data, "pr", [0], ps).counts[2], [1, 0, 0]);
    assert.deepEqual(openedByPeriod(data, "issue", [], ps).counts.flat().reduce((a, b) => a + b), 0);
    // Periods ending in the last 7 days (from 2022-01-25) may still change.
    assert.deepEqual(issues.periods.map((p) => !!p.provisional), [false, false, false, false, true, true]);
    assert.equal(periodNote(issues.periods[5]), " (partial, provisional)");
    assert.equal(periodNote(issues.periods[4]), " (provisional)");
  }
});
