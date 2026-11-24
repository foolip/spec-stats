import { test } from "node:test";
import assert from "node:assert/strict";
import { Calendar, isoWeek, formatCount, standardDate } from "../src/lib/dates.ts";
import { fromRaw, type RawData } from "../src/lib/data.ts";
import { buckets, periodName, resolveBin } from "../src/lib/bins.ts";
import { formatUrl, parseUrl, presetOf, presetRange, defaultState } from "../src/lib/state.ts";
import { computeModel } from "../src/lib/model.ts";

const win = { from: "2022-01-01", to: "2026-11-23" };
const cal = new Calendar(win.from);
const BASE = "/spec-stats";
const specs = ["dom", "html"];

test("dates", () => {
  assert.equal(cal.day("2022-01-01"), 0);
  assert.equal(cal.iso(cal.day("2026-11-23")), "2026-11-23");
  assert.ok(Number.isNaN(cal.day("2026-02-30")));
  assert.deepEqual(isoWeek(new Date(Date.UTC(2026, 10, 17))), { year: 2026, week: 47 });
  assert.deepEqual(isoWeek(new Date(Date.UTC(2021, 0, 3))), { year: 2020, week: 53 });
  assert.deepEqual(isoWeek(new Date(Date.UTC(2024, 11, 30))), { year: 2025, week: 1 });
  assert.equal(formatCount(1234567), "1,234,567");
  assert.equal(formatCount(-12), "−12");
  assert.equal(standardDate(cal.date(cal.day("2026-11-23"))), "23 November 2026");
});

test("bins", () => {
  const from = cal.day("2025-11-24");
  const to = cal.day("2026-11-23");
  assert.equal(resolveBin(cal, from, to, "auto"), "week");
  assert.equal(resolveBin(cal, cal.day("2023-11-24"), to, "auto"), "month");
  assert.equal(resolveBin(cal, 0, to, "auto"), "quarter");
  const weeks = buckets(cal, from, to, "week");
  assert.equal(weeks[0].start, from);
  assert.equal(weeks.at(-1)!.end, to);
  for (let i = 1; i < weeks.length; i++) assert.equal(weeks[i].start, weeks[i - 1].end + 1);
  assert.equal(weeks[0].partial, false); // 2025-11-24 is a Monday
  assert.equal(weeks.at(-1)!.partial, true); // 2026-11-23 is a Monday
  assert.equal(periodName(cal, cal.day("2026-11-17"), "week"), "2026-W47");
  assert.equal(periodName(cal, cal.day("2026-11-01"), "month"), "November 2026");
  assert.equal(periodName(cal, cal.day("2026-10-01"), "quarter"), "2026 Q4");
  assert.equal(periodName(cal, cal.day("2026-11-17"), "day"), "Tue, Nov 17, 2026");
});

test("URL state round-trips, with defaults left out", () => {
  const d = defaultState(win, "reviews", "html");
  assert.equal(cal.iso(d.from), "2025-11-24");
  assert.equal(formatUrl(d, win, BASE), "/spec-stats/reviews/html/");
  assert.deepEqual(parseUrl("/spec-stats/reviews/html/", "", win, specs, BASE), d);
  const three = { ...d, ...presetRange(win, "3years"), bin: "month" as const };
  const url = formatUrl(three, win, BASE);
  assert.equal(url, "/spec-stats/reviews/html/?from=2023-11-24&to=2026-11-23&bin=month");
  const u = new URL(url, "http://x");
  assert.deepEqual(parseUrl(u.pathname, u.search, win, specs, BASE), three);
  assert.equal(presetOf(win, three.from, three.to), "3years");
});

test("URL parsing drops unknown values and clamps dates", () => {
  const s = parseUrl("/spec-stats/nope/nfc/", "?bin=year&x=1&from=2020-01-01&to=2030-01-01", win, specs, BASE);
  assert.equal(s.view, "issues");
  assert.equal(s.spec, null);
  assert.equal(s.bin, "auto");
  assert.equal(s.from, 0);
  assert.equal(s.to, cal.day(win.to));
  const root = parseUrl("/spec-stats/", "", win, specs, BASE);
  assert.equal(formatUrl(root, win, BASE), "/spec-stats/issues/");
});

// A small window: 2026-01-01 to 2026-01-31, two repos.
function fixture(): RawData {
  // [repo, number, kind, created, closed (days after created), later_in_day]
  const rows: [number, number, number, number, number | null, number][] = [
    [0, 1, 0, -400, null, 0], // an issue open since before 2025, all window
    [0, 2, 0, 3, 5, 1], // closed on day 8, 6 days open
    [0, 3, 0, 10, null, 0], // open at the window's end
    [0, 4, 2, 2, 1, 0], // PR merged in 1 day
    [0, 5, 1, 4, 20, 0], // PR closed without merging
    [1, 1, 0, -10, 15, 0], // created before the window, closed on day 5
    [1, 2, 2, 20, 9, 1], // merged in 10 days on day 29
    [1, 3, 1, 28, null, 0], // open PR
  ];
  rows.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const raw: RawData = {
    meta: { from: "2026-01-01", to: "2026-01-31" },
    repos: { name: ["dom", "html"], standard: ["DOM", "HTML"] },
    items: { repo: [], number: [], kind: [], created: [], closed: [], later_in_day: [] },
  };
  const last = new Map<number, [number, number]>();
  for (const [repo, number, kind, created, closed, later] of rows) {
    const prev = last.get(repo);
    raw.items.repo.push(repo);
    raw.items.number.push(prev ? number - prev[0] : number);
    raw.items.created.push(prev ? created - prev[1] : created);
    raw.items.kind.push(kind);
    raw.items.closed.push(closed);
    raw.items.later_in_day.push(later);
    last.set(repo, [number, created]);
  }
  return raw;
}

test("decoding", () => {
  const data = fromRaw(fixture());
  assert.equal(data.end, 30);
  assert.deepEqual([...data.items.number], [1, 2, 3, 4, 5, 1, 2, 3]);
  assert.deepEqual([...data.items.created], [-400, 3, 10, 2, 4, -10, 20, 28]);
  assert.equal(data.items.closedDay[1], 8);
  assert.equal(data.items.openDays[1], 6);
  assert.equal(data.items.closedDay[2], Infinity);
});

test("model: issues", () => {
  const data = fromRaw(fixture());
  const m = computeModel(data, { view: "issues", spec: null, from: 0, to: 30, bin: "day" }, { daily: true });
  // Open at the end of day 0: dom#1, html#1. Day 3: + dom#2. Day 5: html#1 closed. Day 8: dom#2 closed. Day 10: + dom#3.
  const total = m.daily!.total;
  assert.equal(total[0], 2);
  assert.equal(total[3], 3);
  assert.equal(total[5], 2);
  assert.equal(total[8], 1);
  assert.equal(total[10], 2);
  assert.equal(total[30], 2);
  assert.equal(m.tiles.open, 2);
  assert.equal(m.tiles.openBefore, 2); // dom#1 and html#1, created before the window
  assert.equal(m.tiles.closed, 2);
  assert.equal(m.tiles.opened, 2);
  const opened = m.opened.reduce((a, b) => a.map((v, i) => v + b.values[i]), [0, 0, 0]);
  assert.deepEqual(opened, [1, 0, 1]); // still open, closed later, within a week
  const closed = m.closed.reduce((a, b) => a.map((v, i) => v + b.values[i]), [0, 0, 0]);
  assert.deepEqual(closed, [0, 1, 1]); // html#1 15 days; dom#2 6 days
  assert.equal(m.opened.at(-1)!.provisional, true);
  assert.equal(m.opened[0].provisional, false);
  const html = m.bySpec.find((r) => r.name === "html")!;
  assert.deepEqual([html.open, html.change, html.closed], [0, -1, 1]);
});

test("model: reviews", () => {
  const data = fromRaw(fixture());
  const m = computeModel(data, { view: "reviews", spec: null, from: 0, to: 30, bin: "auto" });
  assert.equal(m.period, "week");
  const closed = m.closed.reduce((a, b) => a.map((v, i) => v + b.values[i]), [0, 0, 0, 0]);
  // dom#4 merged in 1 day; dom#5 closed unmerged; html#2 merged in 9 + 1 = 10 days.
  assert.deepEqual(closed, [0, 1, 1, 1]);
  assert.equal(m.tiles.closed, 2); // merges only
  assert.equal(m.tiles.open, 1);
  const one = computeModel(data, { view: "reviews", spec: "html", from: 0, to: 30, bin: "auto" });
  assert.equal(one.tiles.open, 1);
  assert.equal(one.tiles.closed, 1);
});

test("model doesn't depend on the order of items", () => {
  const raw = fixture();
  const data = fromRaw(raw);
  const state = { view: "issues" as const, spec: null, from: 0, to: 30, bin: "week" as const };
  const a = computeModel(data, state, { daily: true });
  // Shuffle the decoded items.
  const n = data.items.length;
  const order = [...Array(n).keys()].reverse();
  const items = data.items;
  const shuffled = {
    ...data,
    items: {
      length: n,
      repo: Uint16Array.from(order, (i) => items.repo[i]),
      number: Uint32Array.from(order, (i) => items.number[i]),
      kind: Uint8Array.from(order, (i) => items.kind[i]),
      created: Int32Array.from(order, (i) => items.created[i]),
      closedDay: Float64Array.from(order, (i) => items.closedDay[i]),
      openDays: Float64Array.from(order, (i) => items.openDays[i]),
    },
  };
  assert.deepEqual(computeModel(shuffled, state, { daily: true }), a);
});
