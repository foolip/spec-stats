import assert from "node:assert/strict";
import { test } from "node:test";
import { DEFAULT, fixed, parse, rangeDays, selectedRepos, serialize, type Context } from "../src/lib/url.ts";

const ctx: Context = { repoNames: ["dom", "fetch", "html", "url"], from: "2022-01-01", to: "2026-11-17" };

test("the default view is the empty query string", () => {
  assert.deepEqual(parse("", ctx), DEFAULT);
  assert.equal(serialize(DEFAULT), "");
});

test("a view round-trips through the URL", () => {
  const search = "?repos=dom,html&from=2024-01-01&to=2026-11-17&drafts=exclude";
  assert.equal(serialize(parse(search, ctx)), search);
  assert.equal(serialize(parse("?repos=-html&range=1y", ctx)), "?repos=-html&range=1y");
});

test("unknown and invalid parameters are dropped", () => {
  assert.equal(serialize(parse("?view=nope&repos=html,nfc&range=7y&drafts=maybe&utm_source=x", ctx)), "?repos=html");
  assert.equal(serialize(parse("?repos=nfc", ctx)), "");
  assert.equal(serialize(parse("?from=2025-13-45", ctx)), "");
  // Out of the window: clamped to it. Backwards: dropped.
  assert.equal(serialize(parse("?from=2019-01-01&to=2030-01-01", ctx)), "?from=2022-01-01&to=2026-11-17");
  assert.equal(serialize(parse("?from=2025-01-01&to=2024-01-01&range=1y", ctx)), "");
});

test("repos are listed in a fixed order, and excluding every repo means all", () => {
  assert.equal(serialize(parse("?repos=url,dom,dom", ctx)), "?repos=dom,url");
  assert.equal(serialize(parse("?repos=-dom,-fetch,-html,-url", ctx)), "");
});

test("a selection's repos", () => {
  const names = ctx.repoNames;
  assert.deepEqual(selectedRepos({ mode: "all" }, names), [0, 1, 2, 3]);
  assert.deepEqual(selectedRepos({ mode: "only", names: ["html"] }, names), [2]);
  assert.deepEqual(selectedRepos({ mode: "except", names: ["html"] }, names), [0, 1, 3]);
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
