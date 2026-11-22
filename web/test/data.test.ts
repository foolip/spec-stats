import assert from "node:assert/strict";
import { test } from "node:test";
import { fromRaw, type RawData } from "../src/lib/data.ts";

test("the data file is decoded into values, with each event's item", () => {
  const raw: RawData = {
    meta: { from: "2025-01-01", to: "2025-01-31" },
    event_types: ["_carried_in", "_created", "closed", "reopened"],
    repos: { name: ["dom", "html"], standard: ["DOM", "HTML"] },
    items: {
      // dom #10 (opened before the window), html #3, dom #12, html #7: the
      // differences are from the previous item of the same repo.
      repo: [0, 1, 0, 1],
      number: [10, 3, 2, 4],
      is_pr: [1, 1, 0, 1],
      created: [-30, 5, 32, 3],
      hours_to_merge: [null, 2, null, null],
      hours_to_close: [null, null, null, null],
      events: [2, 1, 1, 2],
    },
    events: {
      // #10: carried in, closed on day 4. html #3: created on day 5.
      // dom #12 (created on day 2): reopened on day 9 (a first gap that isn't 0).
      // html #7: created on day 8, closed on day 8.
      day: [0, 4, 0, 7, 0, 0],
      event: [0, 2, 1, 3, 1, 2],
    },
  };
  const data = fromRaw(raw);
  assert.deepEqual([...data.items.number], [10, 3, 12, 7]);
  assert.deepEqual([...data.items.isPr], [1, 1, 0, 1]);
  assert.deepEqual([...data.items.created], [-30, 5, 2, 8]);
  assert.deepEqual([...data.events.item], [0, 0, 1, 2, 3, 3]);
  assert.deepEqual([...data.events.day], [0, 4, 5, 9, 8, 8]);
  assert.deepEqual([...data.events.event], [0, 2, 1, 3, 1, 2]);

  raw.items.events[3] = 3;
  assert.throws(() => fromRaw(raw), /items.events adds up to 7, but there are 6 events/);
});
