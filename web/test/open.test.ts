import assert from "node:assert/strict";
import { test } from "node:test";
import { fromRaw } from "../src/lib/data.ts";
import { ofKind, openByGroup, openByRepo, total, yearCohorts } from "../src/lib/open.ts";
import { encode, shuffled, type Table } from "./helpers.ts";

const TYPES = ["_carried_in", "_carried_in_as_draft", "_created", "_created_as_draft",
  "closed", "reopened", "convert_to_draft", "ready_for_review", "merged"];

test("open and draft PRs are counted at the end of each day", () => {
  const events: [number, number, string][] = [
    [0, 0, "_carried_in"],
    [0, 0, "_carried_in_as_draft"],
    [1, 1, "_created"],
    [2, 0, "ready_for_review"],
    [3, 1, "closed"],
    [3, 1, "reopened"],     // closed and reopened on one day: still open
    [4, 2, "_created"],
    [4, 2, "_created_as_draft"],
    [5, 2, "closed"],       // a draft closed without becoming ready
    [6, 1, "closed"],
    [6, 1, "merged"],       // a merge changes nothing beyond its `closed`
  ];
  const table: Table = {
    meta: { from: "2025-01-01", to: "2025-01-07" },
    event_types: TYPES,
    repos: { name: ["dom", "html"], standard: ["DOM", "HTML"] },
    // #10 opened in 2024, before the window; #20 and #21 in it.
    items: { repo: [0, 1, 1], number: [10, 20, 21], created: [-30, 1, 4], hours_to_merge: [null, 120, null] },
    events,
  };
  const data = fromRaw(encode(table));
  assert.equal(data.days, 7);
  const byRepo = openByRepo(data, "pr");
  assert.deepEqual([...byRepo[0].ready], [0, 0, 1, 1, 1, 1, 1]);
  assert.deepEqual([...byRepo[0].draft], [1, 1, 0, 0, 0, 0, 0]);
  assert.deepEqual([...byRepo[1].ready], [0, 1, 1, 1, 1, 1, 0]);
  assert.deepEqual([...byRepo[1].draft], [0, 0, 0, 0, 1, 0, 0]);
  const all = total(byRepo, [0, 1], data.days);
  assert.deepEqual([...all.ready], [0, 1, 2, 2, 2, 2, 1]);
  assert.deepEqual([...all.draft], [1, 1, 0, 0, 1, 0, 0]);

  // By year opened: the last 2 years, and one group before them.
  const cohorts = yearCohorts(data, 2);
  assert.deepEqual(cohorts.labels, ["older", "2024", "2025"]);
  assert.deepEqual([...cohorts.of], [1, 2, 2]);
  const byGroup = openByGroup(data, cohorts.of, 3);
  assert.deepEqual([...byGroup[0][1].ready], [...byRepo[0].ready]);
  assert.deepEqual([...byGroup[1][2].ready], [...byRepo[1].ready]);
  assert.deepEqual([...byGroup[1][0].ready], [0, 0, 0, 0, 0, 0, 0]);
  assert.ok(Number.isNaN(data.items.hoursToMerge[0]));
  assert.equal(data.items.hoursToMerge[1], 120);

  // The order of items and events makes no difference.
  const other = fromRaw(encode(shuffled(table)));
  assert.deepEqual(openByRepo(other, "pr"), byRepo);
  assert.deepEqual(openByGroup(other, yearCohorts(other, 2).of, 3), byGroup);
});

test("open issues and open PRs are counted apart", () => {
  const table: Table = {
    meta: { from: "2025-01-01", to: "2025-01-05" },
    event_types: TYPES,
    repos: { name: ["dom"], standard: ["DOM"] },
    // #1 an issue carried in, #2 a PR, #3 an issue created on day 2.
    items: {
      repo: [0, 0, 0],
      number: [1, 2, 3],
      is_pr: [0, 1, 0],
      created: [-30, 1, 2],
      hours_to_merge: [null, null, null],
      hours_to_close: [null, null, 72],
    },
    events: [
      [0, 0, "_carried_in"],
      [1, 1, "_created"],
      [2, 2, "_created"],
      [3, 0, "closed"],
      [4, 0, "reopened"],
      [4, 1, "convert_to_draft"],
      [4, 2, "closed"],
    ],
  };
  const data = fromRaw(encode(table));
  assert.deepEqual([...data.items.isPr], [0, 1, 0]);
  assert.equal(data.items.hoursToClose[2], 72);
  assert.ok(Number.isNaN(data.items.hoursToClose[0]));
  const issues = openByRepo(data, "issue")[0];
  assert.deepEqual([...issues.ready], [1, 1, 2, 1, 1]);
  assert.deepEqual([...issues.draft], [0, 0, 0, 0, 0]);
  const prs = openByRepo(data, "pr")[0];
  assert.deepEqual([...prs.ready], [0, 1, 1, 1, 0]);
  assert.deepEqual([...prs.draft], [0, 0, 0, 0, 1]);
  // Items of the other kind are left out of every group.
  const byGroup = openByGroup(data, ofKind(data, "issue"), 1);
  assert.deepEqual(byGroup[0][0], issues);
  const other = fromRaw(encode(shuffled(table)));
  assert.deepEqual(openByRepo(other, "issue")[0], issues);
});
