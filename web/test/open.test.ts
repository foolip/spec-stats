import assert from "node:assert/strict";
import { test } from "node:test";
import { fromRaw } from "../src/lib/data.ts";
import { ofKind, openByGroup, openByRepo, total, yearCohorts } from "../src/lib/open.ts";
import { encode, shuffled, type Table } from "./helpers.ts";

test("open PRs are counted at the end of each day, from creation to the last close", () => {
  const table: Table = {
    meta: { from: "2025-01-01", to: "2025-01-07" },
    repos: { name: ["dom", "html"], standard: ["DOM", "HTML"] },
    // dom #10 opened in 2024, before the window, and still open; html #20
    // created on day 1 and merged on day 6; html #21 created on day 4 and
    // closed on day 5; html #22 created and closed on day 3.
    items: {
      repo: [0, 1, 1, 1],
      number: [10, 20, 21, 22],
      kind: [1, 2, 1, 1],
      created: [-30, 1, 4, 3],
      closed: [null, 6, 5, 3],
    },
  };
  const data = fromRaw(encode(table));
  assert.equal(data.days, 7);
  const byRepo = openByRepo(data, "pr");
  assert.deepEqual([...byRepo[0]], [1, 1, 1, 1, 1, 1, 1]);
  assert.deepEqual([...byRepo[1]], [0, 1, 1, 1, 2, 1, 0]);
  assert.deepEqual([...total(byRepo, [0, 1], data.days)], [1, 2, 2, 2, 3, 2, 1]);
  assert.deepEqual([...total(byRepo, [1], data.days)], [...byRepo[1]]);

  // By year opened: the last 2 years, and one group before them.
  const cohorts = yearCohorts(data, 2);
  assert.deepEqual(cohorts.labels, ["older", "2024", "2025"]);
  assert.deepEqual([...cohorts.of], [1, 2, 2, 2]);
  const byGroup = openByGroup(data, cohorts.of, 3);
  assert.deepEqual([...byGroup[0][1]], [...byRepo[0]]);
  assert.deepEqual([...byGroup[1][2]], [...byRepo[1]]);
  assert.deepEqual([...byGroup[1][0]], [0, 0, 0, 0, 0, 0, 0]);

  // The order of items makes no difference.
  const other = fromRaw(encode(shuffled(table)));
  assert.deepEqual(openByRepo(other, "pr"), byRepo);
  assert.deepEqual(openByGroup(other, yearCohorts(other, 2).of, 3), byGroup);
});

test("open issues and open PRs are counted apart", () => {
  const table: Table = {
    meta: { from: "2025-01-01", to: "2025-01-05" },
    repos: { name: ["dom"], standard: ["DOM"] },
    // #1 an issue opened before the window, closed on day 4; #2 a PR; #3 an
    // issue created on day 2 and closed on day 4, 2 days and a bit later.
    items: {
      repo: [0, 0, 0],
      number: [1, 2, 3],
      kind: [0, 1, 0],
      created: [-30, 1, 2],
      closed: [4, null, 4],
      later_in_day: [0, 0, 1],
    },
  };
  const data = fromRaw(encode(table));
  assert.deepEqual([...data.items.isPr], [0, 1, 0]);
  assert.equal(data.items.daysOpen[2], 3);
  assert.ok(Number.isNaN(data.items.daysOpen[1]));
  const issues = openByRepo(data, "issue")[0];
  assert.deepEqual([...issues], [1, 1, 2, 2, 0]);
  assert.deepEqual([...openByRepo(data, "pr")[0]], [0, 1, 1, 1, 1]);
  // Items of the other kind are left out of every group.
  assert.deepEqual(openByGroup(data, ofKind(data, "issue"), 1)[0][0], issues);
  const other = fromRaw(encode(shuffled(table)));
  assert.deepEqual(openByRepo(other, "issue")[0], issues);
});
