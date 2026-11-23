import assert from "node:assert/strict";
import { test } from "node:test";
import { DEFAULT, href, pagePath, parse, presetRange, query, rangeDays, rangePreset, selectedRepos, type Context } from "../src/lib/url.ts";

const ctx: Context = { repoNames: ["dom", "fetch", "html", "url"], from: "2022-01-01", to: "2026-11-17" };

/** A URL relative to the site's root, read and written back. */
function round(url: string): string {
  const i = url.indexOf("?");
  return i < 0 ? href(parse(url, "", ctx)) : href(parse(url.slice(0, i), url.slice(i), ctx));
}

test("the default view is issues/, with no query string", () => {
  assert.deepEqual(parse("issues/", "", ctx), DEFAULT);
  assert.equal(href(DEFAULT), "issues/");
  // The site's root is the default view too.
  assert.deepEqual(parse("", "", ctx), DEFAULT);
  assert.equal(round(""), "issues/");
  assert.equal(round("?from=2024-01-01&to=2025-01-01"), "issues/?from=2024-01-01&to=2025-01-01");
});

test("the view and spec are in the path, the rest in the query string", () => {
  assert.equal(parse("reviews/html/", "", ctx).repo, "html");
  assert.equal(round("reviews/html/?from=2024-01-01&to=2025-01-01"), "reviews/html/?from=2024-01-01&to=2025-01-01");
  assert.equal(round("reviews/dom/?bin=month&to=2025-01-01&from=2022-01-01"), "reviews/dom/?from=2022-01-01&to=2025-01-01&bin=month");
  assert.equal(round("reviews/html"), "reviews/html/");
  assert.equal(pagePath({ view: "open-prs", repo: "url" }), "reviews/url/");
  assert.equal(query({ ...DEFAULT, repo: "url" }), "");
  // The default range, the last year, is left out.
  assert.equal(parse("reviews/dom/", "", ctx).range, null);
});

test("each view has its own path", () => {
  assert.equal(parse("issues/", "", ctx).view, "open-issues");
  assert.deepEqual(parse("issues/html/", "?from=2024-01-01&to=2025-01-01", ctx), {
    ...DEFAULT,
    view: "open-issues",
    repo: "html",
    range: { from: "2024-01-01", to: "2025-01-01" },
  });
  assert.equal(pagePath({ view: "open-issues", repo: null }), "issues/");
  assert.equal(pagePath({ view: "open-issues", repo: "url" }), "issues/url/");
});

test("every page's path is read back as itself", () => {
  for (const view of ["issues", "reviews"]) {
    for (const path of [`${view}/`, ...ctx.repoNames.map((r) => `${view}/${r}/`)]) assert.equal(round(path), path);
  }
});

test("the bars' period is in the URL, auto by default", () => {
  assert.equal(parse("reviews/", "", ctx).bin, "auto");
  assert.equal(round("reviews/?bin=quarter"), "reviews/?bin=quarter");
  assert.equal(round("reviews/html/?bin=day"), "reviews/html/?bin=day");
  assert.equal(round("reviews/?bin=auto"), "reviews/");
  assert.equal(round("reviews/?bin=fortnight"), "reviews/");
});

test("unknown and invalid parameters are dropped", () => {
  assert.equal(round("reviews/html/?view=nope&range=7y&drafts=maybe&utm_source=x"), "reviews/html/");
  // Old parameters are unknown too.
  assert.equal(round("reviews/?repo=dom"), "reviews/");
  assert.equal(round("reviews/?range=2024-01-01..2026-11-17"), "reviews/");
  assert.equal(round("reviews/?range=3y"), "reviews/");
  // Invalid or backwards dates: the default.
  assert.equal(round("reviews/?from=2025-13-45&to=2026-01-01"), "reviews/");
  assert.equal(round("reviews/?from=2025-01-01&to=soon"), "reviews/");
  assert.equal(round("reviews/?from=2025-01-01&to=2024-01-01"), "reviews/");
});

test("dates are from and to, as on GitHub; an end left out is the window's", () => {
  assert.equal(round("reviews/?from=2024-01-01"), "reviews/?from=2024-01-01&to=2026-11-17");
  assert.equal(round("reviews/?to=2024-01-01"), "reviews/?from=2022-01-01&to=2024-01-01");
  assert.equal(round("reviews/?from=2024-01-01&to=2024-01-01"), "reviews/?from=2024-01-01&to=2024-01-01");
  // Out of the window: clamped to it.
  assert.equal(round("reviews/?from=2019-01-01&to=2030-01-01"), "reviews/?from=2022-01-01&to=2026-11-17");
});

test("the Period choices set dates, except the default", () => {
  assert.equal(presetRange("1y", ctx), null);
  assert.deepEqual(presetRange("3y", ctx), { from: "2023-11-18", to: "2026-11-17" });
  assert.deepEqual(presetRange("all", ctx), { from: "2022-01-01", to: "2026-11-17" });
  for (const p of ["1y", "3y", "all"] as const) assert.equal(rangePreset(presetRange(p, ctx), ctx), p);
  // The last year's dates, fixed, are still that choice.
  assert.equal(rangePreset({ from: "2025-11-18", to: "2026-11-17" }, ctx), "1y");
  // Dates from before the data was updated are no choice.
  assert.equal(rangePreset({ from: "2023-11-17", to: "2026-11-16" }, ctx), null);
});

test("a state's repos", () => {
  const names = ctx.repoNames;
  assert.deepEqual(selectedRepos(null, names), [0, 1, 2, 3]);
  assert.deepEqual(selectedRepos("html", names), [2]);
});

test("presets are relative to the end of the window", () => {
  const last = rangeDays(presetRange("all", ctx), ctx)[1];
  assert.equal(last, 1781);
  const [a, b] = rangeDays(null, ctx);
  assert.equal(b, last);
  assert.equal(b - a + 1, 365);
  const [c, d] = rangeDays(presetRange("3y", ctx), ctx);
  assert.equal(d, last);
  // 2023-11-18 to 2025-11-18, across 2024-02-29.
  assert.equal(a - c, 366 + 365);
});
