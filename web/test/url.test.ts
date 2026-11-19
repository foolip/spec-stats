import assert from "node:assert/strict";
import { test } from "node:test";
import { DEFAULT, fixed, parse, rangeDays, selectedRepos, serialize, type Context } from "../src/lib/url.ts";

const ctx: Context = { repoNames: ["dom", "fetch", "html", "url"], from: "2022-01-01", to: "2026-11-17" };

test("the default view is the empty query string", () => {
  assert.deepEqual(parse("", ctx), DEFAULT);
  assert.equal(serialize(DEFAULT), "");
});

test("a view round-trips through the URL", () => {
  const search = "?repo=html&from=2024-01-01&to=2026-11-17";
  assert.equal(serialize(parse(search, ctx)), search);
  assert.equal(serialize(parse("?repo=dom&range=all", ctx)), "?repo=dom&range=all");
  // The default range, the last year, is left out.
  assert.deepEqual(parse("?repo=dom", ctx).range, { preset: "1y" });
  assert.equal(serialize(parse("?repo=dom&range=1y", ctx)), "?repo=dom");
});

test("unknown and invalid parameters are dropped", () => {
  assert.equal(serialize(parse("?view=nope&repo=html&range=7y&drafts=maybe&utm_source=x", ctx)), "?repo=html");
  assert.equal(serialize(parse("?repo=nfc", ctx)), "");
  // Lists and exclusions aren't supported: all repos.
  assert.equal(serialize(parse("?repo=dom,html", ctx)), "");
  assert.equal(serialize(parse("?repo=-html", ctx)), "");
  assert.equal(serialize(parse("?repos=html", ctx)), "");
  assert.equal(serialize(parse("?from=2025-13-45", ctx)), "");
  // Out of the window: clamped to it. Backwards: dropped.
  assert.equal(serialize(parse("?from=2019-01-01&to=2030-01-01", ctx)), "?from=2022-01-01&to=2026-11-17");
  assert.equal(serialize(parse("?from=2025-01-01&to=2024-01-01&range=1y", ctx)), "");
});

test("a state's repos", () => {
  const names = ctx.repoNames;
  assert.deepEqual(selectedRepos(null, names), [0, 1, 2, 3]);
  assert.deepEqual(selectedRepos("html", names), [2]);
});

test("presets are relative to the end of the window; links fix them", () => {
  const last = rangeDays({ preset: "all" }, ctx)[1];
  assert.equal(last, 1781);
  const [a, b] = rangeDays({ preset: "1y" }, ctx);
  assert.equal(b, last);
  assert.deepEqual(fixed({ preset: "1y" }, ctx), { from: "2025-11-18", to: "2026-11-17" });
  assert.equal(b - a + 1, 365);
  assert.deepEqual(fixed({ preset: "3m" }, ctx), { from: "2026-08-18", to: "2026-11-17" });
});
