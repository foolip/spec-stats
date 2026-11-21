// `npm run cwv`: checks the built site (dist/, from `npm run build`) for
// Core Web Vitals regressions, in Chromium, and fails if any budget is
// broken (docs/site-design.md, "Performance checks"). Run in CI before
// every publish (.github/workflows/site.yml).
//
// Lab checks, not field data. Timings depend on the machine, so they have
// generous budgets; what the page's design guarantees is checked exactly:
//
// - CLS: 0 on every load, across sizes, light and dark, slow and fast
//   loads, links with and without a query string, scrolling and every
//   control. Shifts within 500 ms of input don't count, as in CLS.
// - LCP: under a throttled phone (Lighthouse's Slow 4G, CPU 4× slower), at
//   the first paint, which needs only the HTML: no render-blocking
//   request, the HTML within the first round trip, and every request
//   started by the HTML itself, so there's no chain. Plus a time budget.
// - INP: the slowest response to a control, at full CPU speed.
//
// dist/ is served as GitHub Pages serves it: gzipped, under SITE_BASE,
// with 404.html for unknown paths. The browser is Chrome for Testing, the
// full Chrome that Playwright pins to its version (`npx playwright install
// --no-shell chromium`), in Chrome's headless mode: not Playwright's
// default for headless, Chrome Headless Shell, a separate build. Set
// CHROMIUM_PATH to run another Chrome.

import { readFileSync, existsSync, statSync } from "node:fs";
import { createServer, type Server } from "node:http";
import { dirname, extname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";
import { chromium, type Browser, type BrowserContext, type Page } from "playwright";

const BUDGETS = {
  /** LCP on the throttled phone, median of the runs: about 0.35 s now. */
  lcpMs: 1000,
  /** LCP no later than the first paint (plus a frame or so). */
  lcpAfterFirstPaintMs: 50,
  /** The HTML, gzipped: what fits in the first round trip. */
  htmlBytes: 14 * 1024,
  /** INP at full CPU speed: Google's "good" limit. About 60 ms now. */
  inpMs: 200,
};

const web = dirname(dirname(fileURLToPath(import.meta.url)));
const dist = join(web, "dist");
const base = process.env.SITE_BASE ?? "/spec-stats/";
const failures: string[] = [];

function check(ok: boolean, message: string) {
  if (!ok) failures.push(message);
}

// The URLs checked: each kind of page, and links with a query string, which
// load a page prerendered for other values.
const URLS = ["reviews/", "reviews/html/", "reviews/?range=3y&bin=month", "reviews/dom/?range=2024-01-01..2024-06-30"];

const TYPES: Record<string, string> = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".json": "application/json",
  ".svg": "image/svg+xml",
};

function serve(): Promise<Server> {
  return new Promise((resolve) => {
    const server = createServer((req, res) => {
      const url = new URL(req.url ?? "/", "http://localhost");
      if (!url.pathname.startsWith(base)) return void res.writeHead(404).end();
      const path = url.pathname.slice(base.length - 1);
      let file = join(dist, path);
      let status = 200;
      if (existsSync(file) && statSync(file).isDirectory()) {
        if (!path.endsWith("/")) return void res.writeHead(301, { Location: `${url.pathname}/${url.search}` }).end();
        file = join(file, "index.html");
      }
      if (!existsSync(file)) [file, status] = [join(dist, "404.html"), 404];
      res.writeHead(status, {
        "Content-Type": TYPES[extname(file)] ?? "application/octet-stream",
        "Content-Encoding": "gzip",
        "Cache-Control": "max-age=600",
      });
      res.end(gzipSync(readFileSync(file)));
    });
    server.listen(0, () => resolve(server));
  });
}

interface Throttle {
  slow: boolean;
}

async function open(browser: Browser, viewport: { width: number; height: number }, { slow }: Throttle, colorScheme: "light" | "dark" = "light") {
  // No touch emulation: Chromium then marks every shift as after input.
  const context = await browser.newContext({ viewport, colorScheme });
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  await cdp.send("Network.enable");
  if (slow) {
    await cdp.send("Network.emulateNetworkConditions", {
      offline: false,
      latency: 150,
      downloadThroughput: (1.6e6 / 8) * 0.9,
      uploadThroughput: (750e3 / 8) * 0.9,
    });
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
  }
  await page.addInitScript(() => {
    const w = window as unknown as { cwv: { cls: number; shifts: string[]; lcp: number; inp: number; inpOn: string } };
    const cwv = (w.cwv = { cls: 0, shifts: [] as string[], lcp: 0, inp: 0, inpOn: "" });
    new PerformanceObserver((list) => {
      for (const e of list.getEntries() as (PerformanceEntry & { value: number; hadRecentInput: boolean; sources: { node?: Node }[] })[]) {
        if (e.hadRecentInput) continue;
        cwv.cls += e.value;
        cwv.shifts.push(`${Math.round(e.startTime)} ms: ${e.sources.map((s) => (s.node as Element | undefined)?.className || s.node?.nodeName).join(", ")}`);
      }
    }).observe({ type: "layout-shift", buffered: true });
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) cwv.lcp = e.startTime;
    }).observe({ type: "largest-contentful-paint", buffered: true });
    new PerformanceObserver((list) => {
      for (const e of list.getEntries() as (PerformanceEntry & { interactionId: number; target: Element | null })[]) {
        if (e.interactionId && e.duration > cwv.inp) {
          const t = e.target as HTMLElement | null;
          [cwv.inp, cwv.inpOn] = [e.duration, `${e.name} on ${t?.dataset.control ?? t?.dataset.preset ?? t?.textContent?.trim().slice(0, 20) ?? "?"}`];
        }
      }
    }).observe({ type: "event", durationThreshold: 16, buffered: true } as PerformanceObserverInit); // durationThreshold: Event Timing
  });
  return { context, page, cdp };
}

async function loaded(page: Page) {
  await page.waitForSelector(".chart svg path", { timeout: 60_000 });
  await page.waitForTimeout(500);
}

const result = (page: Page) =>
  page.evaluate(() => (window as unknown as { cwv: { cls: number; shifts: string[]; lcp: number; inp: number; inpOn: string } }).cwv);

/** Every control once, with real input: the date presets, both selects by
 * keyboard, and a spec in the by-spec table. */
async function useControls(page: Page) {
  for (const preset of ["all", "3y", "1y"]) {
    await page.locator(`[data-preset="${preset}"]`).click();
    await page.waitForTimeout(600);
  }
  for (const select of await page.locator("select").all()) {
    await select.focus();
    await page.keyboard.press("ArrowDown");
    await page.waitForTimeout(600);
  }
  const spec = page.locator("button.spec");
  if (await spec.count()) {
    await spec.first().click();
    await page.waitForTimeout(600);
  }
}

const median = (xs: number[]) => [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)];

async function lcpChecks(browser: Browser, origin: string) {
  console.log("LCP, throttled phone (Slow 4G, CPU 4x), 3 cold loads each:");
  for (const path of URLS) {
    const lcps: number[] = [];
    for (let run = 0; run < 3; run++) {
      const { context, page, cdp } = await open(browser, { width: 412, height: 823 }, { slow: true });
      const started: { url: string; by: string }[] = [];
      cdp.on("Network.requestWillBeSent", (e) => started.push({ url: e.request.url, by: e.initiator.type }));
      const response = await page.goto(origin + path);
      await loaded(page);
      const timing = await page.evaluate(() => ({
        fcp: performance.getEntriesByName("first-contentful-paint")[0]?.startTime ?? 0,
        html: (performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming).transferSize,
        blocking: (performance.getEntriesByType("resource") as (PerformanceResourceTiming & { renderBlockingStatus?: string })[])
          .filter((r) => r.renderBlockingStatus === "blocking")
          .map((r) => r.name),
      }));
      const { lcp, cls, shifts } = await result(page);
      await context.close();
      lcps.push(lcp);
      check(response?.ok() ?? false, `${path}: HTTP ${response?.status()}`);
      check(lcp - timing.fcp <= BUDGETS.lcpAfterFirstPaintMs, `${path}: LCP at ${Math.round(lcp)} ms, after the first paint at ${Math.round(timing.fcp)} ms: the largest content isn't in the first paint`);
      check(timing.blocking.length === 0, `${path}: render-blocking requests: ${timing.blocking.join(", ")}`);
      check(timing.html <= BUDGETS.htmlBytes, `${path}: HTML is ${timing.html} bytes, over ${BUDGETS.htmlBytes}`);
      // The tab icon is fetched by the browser itself, after the page.
      const chained = started.slice(1).filter((r) => !r.url.startsWith("data:") && r.by !== "parser" && !r.url.endsWith("/favicon.svg"));
      check(chained.length === 0, `${path}: requests not started by the HTML (a chain): ${chained.map((r) => `${r.url} (${r.by})`).join(", ")}`);
      check(cls === 0, `${path}: CLS ${cls.toFixed(4)} on a throttled phone: ${shifts.join("; ")}`);
      const requests = started.filter((r) => !r.url.startsWith("data:")).map((r) => r.url.split("/").filter(Boolean).pop());
      if (run === 0) console.log(`  ${path.padEnd(44)} HTML ${(timing.html / 1024).toFixed(1)} KB; requests: ${requests.join(", ")}`);
    }
    const lcp = median(lcps);
    console.log(`  ${path.padEnd(44)} LCP ${lcps.map((x) => Math.round(x)).join(", ")} ms`);
    check(lcp <= BUDGETS.lcpMs, `${path}: LCP ${Math.round(lcp)} ms, over ${BUDGETS.lcpMs} ms`);
  }
}

async function clsChecks(browser: Browser, origin: string) {
  const sizes = [
    { width: 360, height: 640 },
    { width: 412, height: 823 },
    { width: 768, height: 1024 },
    { width: 1350, height: 940 },
    { width: 1920, height: 1080 },
    { width: 640, height: 360 },
  ];
  // Every size, speed and URL is loaded and scrolled; the controls are used
  // once per size (each use takes seconds).
  const cases: { size: (typeof sizes)[number]; slow: boolean; scheme: "light" | "dark"; path: string; controls: boolean }[] = [];
  for (const size of sizes) {
    for (const slow of [true, false]) for (const path of URLS) cases.push({ size, slow, scheme: "light", path, controls: false });
    cases.push({ size, slow: false, scheme: "light", path: URLS[0], controls: true });
  }
  for (const path of URLS) cases.push({ size: sizes[1], slow: true, scheme: "dark", path, controls: false });
  let worst = 0;
  for (const c of cases) {
    const { context, page } = await open(browser, c.size, { slow: c.slow }, c.scheme);
    await page.goto(origin + c.path);
    await loaded(page);
    await page.mouse.wheel(0, 10_000);
    await page.waitForTimeout(400);
    await page.evaluate(() => scrollTo(0, 0));
    await page.waitForTimeout(300);
    if (c.controls) await useControls(page);
    const { cls, shifts } = await result(page);
    await context.close();
    worst = Math.max(worst, cls);
    const name = `${c.path} at ${c.size.width}×${c.size.height}, ${c.scheme}, ${c.slow ? "slow" : "fast"}${c.controls ? ", controls used" : ""}`;
    check(cls === 0, `${name}: CLS ${cls.toFixed(4)}: ${shifts.join("; ")}`);
  }
  console.log(`CLS: ${cases.length} loads, scrolled, every control used on ${sizes.length}: worst ${worst.toFixed(4)}`);
}

async function inpChecks(browser: Browser, origin: string) {
  const report: string[] = [];
  // At 4x, choosing days for a year redraws 365 bars and table rows: slow,
  // but the user asked for it. Reported, not enforced.
  for (const [label, slow] of [["full CPU", false], ["CPU 4x (not enforced)", true]] as const) {
    const { context, page } = await open(browser, { width: 1350, height: 940 }, { slow });
    await page.goto(origin + URLS[0]);
    await loaded(page);
    await useControls(page);
    const { inp, inpOn } = await result(page);
    await context.close();
    report.push(`${label} ${Math.round(inp)} ms (${inpOn || "none over 16 ms"})`);
    if (!slow) check(inp <= BUDGETS.inpMs, `INP ${Math.round(inp)} ms at full CPU speed (${inpOn}), over ${BUDGETS.inpMs} ms`);
  }
  console.log(`INP, slowest response to a control: ${report.join("; ")}`);
}

if (!existsSync(join(dist, "reviews", "index.html"))) {
  console.error("dist/ isn't built: run `npm run build` first");
  process.exit(1);
}
const server = await serve();
const address = server.address();
const origin = `http://127.0.0.1:${typeof address === "object" && address ? address.port : 0}${base}`;
// Real scrollbars, as on Windows and Linux desktops: a page that narrows
// when it starts to scroll shifts.
const browser = await chromium.launch({
  channel: "chromium",
  executablePath: process.env.CHROMIUM_PATH,
  ignoreDefaultArgs: ["--hide-scrollbars"],
});
console.log(`Chrome ${browser.version()}\n`);
try {
  await lcpChecks(browser, origin);
  await clsChecks(browser, origin);
  await inpChecks(browser, origin);
} finally {
  await browser.close();
  server.close();
}

if (failures.length) {
  console.error(`\n${failures.length} Core Web Vitals check(s) failed:`);
  for (const f of failures) console.error(`  - ${f}`);
  process.exit(1);
}
console.log("\nAll Core Web Vitals checks passed.");
