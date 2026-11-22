import assert from "node:assert/strict";
import { test } from "node:test";
import { periodNote, periods } from "../src/lib/bins.ts";
import { fromRaw } from "../src/lib/data.ts";
import { closes, flowByPeriod, merges, openedByPeriod } from "../src/lib/flow.ts";
import { encode, shuffled, type Table } from "./helpers.ts";

const FROM = "2022-01-01";

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
    items: { repo: [0, 1, 0, 0], number: [1, 2, 3, 4], created: [0, 0, 0, 0], hours_to_merge: [24, 3, 25, 241] },
    events: ev,
  };
  const ps = periods(FROM, 0, 30, "week");
  assert.equal(ps[0].first, "2021-12-27");
  // The order of items and events makes no difference.
  for (const data of [fromRaw(encode(table)), fromRaw(encode(shuffled(table)))]) {
    const flow = merges(data);
    assert.deepEqual(flowByPeriod(data, flow, [0], ps).slice(0, 4), [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]);
    assert.deepEqual(flowByPeriod(data, flow, [0, 1], ps)[1], [2, 0, 0]);
    // Only days in the periods count: the merge on day 17 is left out.
    assert.deepEqual(flowByPeriod(data, flow, [0], periods(FROM, 0, 16, "week")).flat().reduce((a, b) => a + b), 2);
  }
});

test("issues are counted at their last close, by time open", () => {
  const types = ["_carried_in", "_created", "closed", "reopened", "merged"];
  const ev: [number, number, string][] = [
    [0, 0, "_created"], [2, 0, "closed"],                      // week 1: within a week
    [0, 1, "_carried_in"], [3, 1, "closed"], [4, 1, "reopened"],
    [10, 1, "closed"],                                         // week 2, once: 1 week–90 days
    [0, 2, "_created"], [3, 2, "closed"], [4, 2, "reopened"],  // reopened: not counted
    [0, 3, "_carried_in"], [17, 3, "closed"],                  // week 3: over 90 days
    [0, 4, "_created"], [9, 4, "closed"], [9, 4, "merged"],    // a PR: not counted
  ];
  const table: Table = {
    meta: { from: FROM, to: "2022-01-31" },
    event_types: types,
    repos: { name: ["html"], standard: ["HTML"] },
    items: {
      repo: [0, 0, 0, 0, 0],
      number: [1, 2, 3, 4, 5],
      is_pr: [0, 0, 0, 0, 1],
      created: [0, -20, 0, -200, 0],
      hours_to_merge: [null, null, null, null, 216],
      hours_to_close: [48, 30 * 24, null, 217 * 24, null],
    },
    events: ev,
  };
  const ps = periods(FROM, 0, 30, "week");
  for (const data of [fromRaw(encode(table)), fromRaw(encode(shuffled(table)))]) {
    assert.deepEqual(flowByPeriod(data, closes(data), [0], ps).slice(0, 4), [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]);
    assert.deepEqual(flowByPeriod(data, merges(data), [0], ps).slice(0, 4), [[0, 0, 0], [0, 0, 0], [0, 1, 0], [0, 0, 0]]);
  }
});

test("items opened are counted per period, by time to close", () => {
  const types = ["_carried_in", "_created", "closed", "reopened", "merged"];
  const ev: [number, number, string][] = [
    [2, 0, "_created"], [2, 0, "closed"],                     // week 1: within 1 day
    [3, 1, "_created"], [8, 1, "closed"],                     // week 1: 1–7 days
    [4, 2, "_created"],                                       // week 1: still open
    [10, 3, "_created"], [30, 3, "closed"],                   // week 2: closed after 7 days
    [0, 4, "_carried_in"], [11, 4, "closed"],                 // opened before the window: not counted
    [10, 5, "_created"], [10, 5, "closed"], [10, 5, "merged"], // a PR: counted only for PRs
    [24, 6, "_created"],                                      // week 4, in the last 7 days
  ];
  const table: Table = {
    meta: { from: FROM, to: "2022-01-31" },
    event_types: types,
    repos: { name: ["html"], standard: ["HTML"] },
    items: {
      repo: [0, 0, 0, 0, 0, 0, 0],
      number: [1, 2, 3, 4, 5, 6, 7],
      is_pr: [0, 0, 0, 0, 0, 1, 0],
      created: [2, 3, 4, 10, -40, 10, 24],
      hours_to_merge: [null, null, null, null, null, 5, null],
      hours_to_close: [3, 24 * 5, null, 24 * 20, 51 * 24, 5, null],
    },
    events: ev,
  };
  const ps = periods(FROM, 0, 30, "week");
  for (const data of [fromRaw(encode(table)), fromRaw(encode(shuffled(table)))]) {
    const issues = openedByPeriod(data, "issue", [0], ps);
    assert.deepEqual(issues.counts.slice(0, 5), [[0, 0, 0], [1, 1, 1], [0, 0, 1], [0, 0, 0], [0, 0, 1]]);
    assert.deepEqual(openedByPeriod(data, "pr", [0], ps).counts[2], [1, 0, 0]);
    assert.deepEqual(openedByPeriod(data, "issue", [], ps).counts.flat().reduce((a, b) => a + b), 0);
    // Periods ending in the last 7 days (from 2022-01-25) may still change.
    assert.deepEqual(issues.periods.map((p) => !!p.provisional), [false, false, false, false, true, true]);
    assert.equal(periodNote(issues.periods[5]), " (partial, provisional)");
    assert.equal(periodNote(issues.periods[4]), " (provisional)");
  }
});
