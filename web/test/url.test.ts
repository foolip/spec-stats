import assert from "node:assert/strict";
import { test } from "node:test";
import { DEFAULT, fixed, href, pagePath, parse, query, rangeDays, selectedRepos, type Context } from "../src/lib/url.ts";

const ctx: Context = { repoNames: ["dom", "fetch", "html", "url"], from: "2022-01-01", to: "2026-11-17" };

/** A URL relative to the site's root, read and written back. */
function round(url: string): string {
  const i = url.indexOf("?");
  return i < 0 ? href(parse(url, "", ctx)) : href(parse(url.slice(0, i), url.slice(i), ctx));
}

test("the default view is reviews/, with no query string", () => {
  assert.deepEqual(parse("reviews/", "", ctx), DEFAULT);
  assert.equal(href(DEFAULT), "reviews/");
  // The site's root is the default view too.
  assert.deepEqual(parse("", "", ctx), DEFAULT);
});

test("the view and spec are in the path, the rest in the query string", () => {
  assert.equal(parse("reviews/html/", "", ctx).repo, "html");
  assert.equal(round("reviews/html/?range=2024-01-01..2026-11-17"), "reviews/html/?range=2024-01-01..2026-11-17");
  assert.equal(round("reviews/dom/?range=all&bin=month"), "reviews/dom/?range=all&bin=month");
  assert.equal(round("reviews/html"), "reviews/html/");
  assert.equal(pagePath({ view: "open-prs", repo: "url" }), "reviews/url/");
  assert.equal(query({ ...DEFAULT, repo: "url" }), "");
  // The default range, the last year, is left out.
  assert.deepEqual(parse("reviews/dom/", "", ctx).range, { preset: "1y" });
  assert.equal(round("reviews/dom/?range=1y"), "reviews/dom/");
});

test("each view has its own path", () => {
  assert.equal(parse("issues/", "", ctx).view, "open-issues");
  assert.deepEqual(parse("issues/html/", "?range=3y", ctx), { ...DEFAULT, view: "open-issues", repo: "html", range: { preset: "3y" } });
  assert.equal(round("issues/html/?range=all&bin=month"), "issues/html/?range=all&bin=month");
  assert.equal(pagePath({ view: "open-issues", repo: null }), "issues/");
  assert.equal(pagePath({ view: "open-issues", repo: "url" }), "issues/url/");
  // An unknown spec: the view's page for every spec.
  assert.equal(round("issues/nfc/"), "issues/");
  assert.equal(round("issues/?repo=dom"), "issues/dom/");
});

test("old ?repo= links go to the spec's page", () => {
  assert.equal(round("?repo=html&range=3y"), "reviews/html/?range=3y");
  assert.equal(round("reviews/?repo=dom"), "reviews/dom/");
  assert.equal(round("?view=open-prs&repo=html"), "reviews/html/");
  // The path wins over the query string.
  assert.equal(round("reviews/url/?repo=dom"), "reviews/url/");
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
  assert.equal(round("reviews/nfc/"), "reviews/");
  assert.equal(round("nope/html/"), "reviews/html/");
  // Lists and exclusions aren't supported: all repos.
  assert.equal(round("?repo=dom,html"), "reviews/");
  assert.equal(round("?repo=-html"), "reviews/");
  assert.equal(round("?repos=html"), "reviews/");
  assert.equal(round("reviews/?range=2025-13-45..2026-01-01"), "reviews/");
  assert.equal(round("reviews/?range=2025-01-01"), "reviews/");
  assert.equal(round("reviews/?range=2025-01-01...2026-01-01"), "reviews/");
  assert.equal(round("reviews/?range=.."), "reviews/");
  // Out of the window: clamped to it. Backwards: dropped.
  assert.equal(round("reviews/?range=2019-01-01..2030-01-01"), "reviews/?range=2022-01-01..2026-11-17");
  assert.equal(round("reviews/?range=2025-01-01..2024-01-01"), "reviews/");
});

test("custom dates are written as in GitHub's search, * for an open end", () => {
  assert.deepEqual(parse("reviews/", "?range=2024-01-01..2025-06-30", ctx).range, { from: "2024-01-01", to: "2025-06-30" });
  assert.equal(round("reviews/?range=2024-01-01..*"), "reviews/?range=2024-01-01..2026-11-17");
  assert.equal(round("reviews/?range=*..2024-01-01"), "reviews/?range=2022-01-01..2024-01-01");
  assert.equal(round("reviews/?range=*..*"), "reviews/?range=2022-01-01..2026-11-17");
  assert.equal(round("reviews/?range=2024-01-01..2024-01-01"), "reviews/?range=2024-01-01..2024-01-01");
  // Unencoded in the URL; encoded, as some tools write it, also read.
  assert.equal(round("reviews/?range=2024-01-01..%2A"), "reviews/?range=2024-01-01..2026-11-17");
});

test("old from and to links still work, rewritten to range", () => {
  assert.equal(round("?repo=html&from=2024-01-01&to=2026-11-17"), "reviews/html/?range=2024-01-01..2026-11-17");
  assert.equal(round("reviews/?from=2024-01-01"), "reviews/?range=2024-01-01..2026-11-17");
  assert.equal(round("reviews/?to=2024-01-01"), "reviews/?range=2022-01-01..2024-01-01");
  assert.equal(round("reviews/?from=2019-01-01&to=2030-01-01"), "reviews/?range=2022-01-01..2026-11-17");
  // A valid range wins; invalid or backwards dates are dropped.
  assert.equal(round("reviews/?range=3y&from=2024-01-01"), "reviews/?range=3y");
  assert.equal(round("reviews/?from=2025-13-45"), "reviews/");
  assert.equal(round("reviews/?from=2025-01-01&to=2024-01-01&range=1y"), "reviews/");
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
  assert.deepEqual(fixed({ preset: "3y" }, ctx), { from: "2023-11-18", to: "2026-11-17" });
});
