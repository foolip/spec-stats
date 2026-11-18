import assert from "node:assert/strict";
import { test } from "node:test";
import { fromRaw, type RawData } from "../src/lib/data.ts";
import { openByRepo, total } from "../src/lib/openprs.ts";

const TYPES = ["_carried_in", "_carried_in_as_draft", "_created", "_created_as_draft",
  "closed", "reopened", "convert_to_draft", "ready_for_review"];
const T = (t: string) => TYPES.indexOf(t);

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
  ];
  const raw: RawData = {
    meta: { from: "2025-01-01", to: "2025-01-07" },
    event_types: TYPES,
    repos: { name: ["dom", "html"], standard: ["DOM", "HTML"] },
    items: { repo: [0, 1, 1], number: [10, 20, 21] },
    events: { day: events.map((e) => e[0]), item: events.map((e) => e[1]), event: events.map((e) => T(e[2])) },
  };
  const data = fromRaw(raw);
  assert.equal(data.days, 7);
  const byRepo = openByRepo(data);
  assert.deepEqual([...byRepo[0].ready], [0, 0, 1, 1, 1, 1, 1]);
  assert.deepEqual([...byRepo[0].draft], [1, 1, 0, 0, 0, 0, 0]);
  assert.deepEqual([...byRepo[1].ready], [0, 1, 1, 1, 1, 1, 1]);
  assert.deepEqual([...byRepo[1].draft], [0, 0, 0, 0, 1, 0, 0]);
  const all = total(byRepo, [0, 1], data.days);
  assert.deepEqual([...all.ready], [0, 1, 2, 2, 2, 2, 2]);
  assert.deepEqual([...all.draft], [1, 1, 0, 0, 1, 0, 0]);
});
