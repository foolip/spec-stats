import assert from "node:assert/strict";
import { test } from "node:test";
import { fromRaw, type RawData } from "../src/lib/data.ts";

test("the data file is decoded into values", () => {
  const raw: RawData = {
    meta: { from: "2025-01-01", to: "2025-01-31" },
    repos: { name: ["dom", "html"], standard: ["DOM", "HTML"] },
    items: {
      // dom #10 (opened before the window), html #3, dom #12, html #7: the
      // differences are from the previous item of the same repo.
      repo: [0, 1, 0, 1],
      number: [10, 3, 2, 4],
      kind: [1, 2, 0, 1],
      created: [-30, 5, 32, 3],
      // dom #10: open. html #3: merged on day 7, after 2 days and a bit.
      // dom #12: closed on day 2, the day it was created. html #7: open.
      closed: [null, 2, 0, null],
      later_in_day: [0, 1, 0, 0],
    },
  };
  const data = fromRaw(raw);
  assert.equal(data.days, 31);
  assert.deepEqual([...data.items.number], [10, 3, 12, 7]);
  assert.deepEqual([...data.items.isPr], [1, 1, 0, 1]);
  assert.deepEqual([...data.items.merged], [0, 1, 0, 0]);
  assert.deepEqual([...data.items.created], [-30, 5, 2, 8]);
  assert.deepEqual([...data.items.closed], [Infinity, 7, 2, Infinity]);
  assert.deepEqual([...data.items.daysOpen], [NaN, 3, 0, NaN]);
});
