// Maintenance load dashboard. Reads only summaries/maintenance.json.

const ACTION_LABELS = {
  review: "Reviews",
  merge: "Merges",
  comment: "Comments on others' issues and PRs",
  pr: "Merged PRs",
  issue: "Issues opened",
};
const ALL = "*";
const COLORED = 6; // categorical slots; the rest fold into Other
const SVG = "http://www.w3.org/2000/svg";

const params = new URLSearchParams(location.search);
const dataUrl = params.get("data") || "../summaries/maintenance.json";

const $ = (id) => document.getElementById(id);
const fmt = new Intl.NumberFormat("en");
const pct = (x) => `${(x * 100).toFixed(x < 0.1 ? 1 : 0)}%`;

function el(tag, attrs = {}, text) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text !== undefined) e.textContent = text;
  return e;
}
function svg(tag, attrs = {}) {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}
function specName(repo) {
  return repo === ALL ? "All specs" : repo.replace(/^whatwg\//, "");
}
function quarterOf(month) {
  const [y, m] = month.split("-").map(Number);
  return `${y} Q${Math.floor((m - 1) / 3) + 1}`;
}

function table(headers, rows, numeric = []) {
  const t = el("table");
  const tr = el("tr");
  headers.forEach((h, i) => tr.append(el("th", numeric.includes(i) ? { class: "num" } : {}, h)));
  const thead = el("thead");
  thead.append(tr);
  t.append(thead);
  const body = el("tbody");
  for (const row of rows) {
    const r = el("tr");
    row.forEach((c, i) => {
      const td = el("td", numeric.includes(i) ? { class: "num" } : {});
      if (c instanceof Node) td.append(c); else td.textContent = c;
      r.append(td);
    });
    body.append(r);
  }
  t.append(body);
  return t;
}

let data;
// Color follows the organization, assigned once from the all-time ranking.
const orgColor = new Map();
let legendOrgs = [];

function displayOrg(org) {
  return orgColor.has(org) ? org : org === "Unknown" ? "Unknown" : "Other";
}

function setup() {
  const named = data.orgs.filter((o) => o !== "Other" && o !== "Unknown");
  named.slice(0, COLORED).forEach((o, i) => orgColor.set(o, `var(--series-${i + 1})`));
  orgColor.set("Other", "var(--series-other)");
  orgColor.set("Unknown", "var(--series-unknown)");
  legendOrgs = [...named.slice(0, COLORED), "Other", "Unknown"];

  const repoSel = $("f-repo");
  for (const r of [ALL, ...data.repos]) repoSel.append(el("option", { value: r }, specName(r)));
  for (const [key, id] of [["spec", "f-repo"], ["activity", "f-action"], ["show", "f-measure"]]) {
    const v = params.get(key);
    if (v && [...$(id).options].some((o) => o.value === v)) $(id).value = v;
    $(id).addEventListener("change", () => {
      params.set(key, $(id).value);
      params.delete("data");
      const q = new URLSearchParams(params);
      if (dataUrl !== "../summaries/maintenance.json") q.set("data", dataUrl);
      history.replaceState(null, "", `?${q}`);
      render();
    });
  }
  const w = data.window;
  $("window-note").textContent =
    `${w.from} through the month before ${w.until}. "People for 50%" is the fewest people who together did half of it.`;
  $("generated").textContent = `Data generated ${data.generated} from the GitHub API.`;
}

function render() {
  const repo = $("f-repo").value;
  const action = $("f-action").value;
  const measure = $("f-measure").value;
  renderChart(repo, action, measure);
  renderConcentration();
  renderPeople(repo, action);
  renderResponse(repo);
}

function renderChart(repo, action, measure) {
  $("chart-title").textContent =
    `${ACTION_LABELS[action]} by organization, per quarter${repo === ALL ? "" : ` (${specName(repo)})`}`;
  // quarter -> org -> count
  const byQ = new Map();
  for (const [month, r, org, a, n] of data.org_monthly) {
    if (a !== action || (repo !== ALL && r !== repo)) continue;
    const q = quarterOf(month);
    if (!byQ.has(q)) byQ.set(q, new Map());
    const m = byQ.get(q);
    const o = displayOrg(org);
    m.set(o, (m.get(o) || 0) + n);
  }
  const quarters = [...byQ.keys()].sort();
  const partialQ = data.partial_month ? quarterOf(data.partial_month) : null;
  const orgs = legendOrgs.filter((o) => quarters.some((q) => byQ.get(q).get(o)));

  const legend = $("legend");
  legend.replaceChildren();
  for (const o of orgs) {
    const li = el("li");
    li.append(el("span", { class: "swatch", style: `background:${orgColor.get(o)}` }), document.createTextNode(o));
    legend.append(li);
  }

  const box = $("chart");
  box.replaceChildren();
  if (!quarters.length) {
    box.append(el("p", { class: "empty" }, "No data for this selection."));
    $("chart-table").replaceChildren();
    return;
  }

  const W = Math.max(box.clientWidth - 32, 280), H = W < 500 ? 260 : 340;
  const padL = 44, padR = 8, padT = 12, padB = 28;
  const totals = quarters.map((q) => [...byQ.get(q).values()].reduce((a, b) => a + b, 0));
  const yMax = measure === "share" ? 1 : niceMax(Math.max(...totals));
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const band = plotW / quarters.length;
  const barW = Math.min(24, band * 0.7);
  const y = (v) => padT + plotH - (v / yMax) * plotH;

  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", "aria-label": $("chart-title").textContent });
  for (const t of ticks(yMax, measure)) {
    s.append(svg("line", { class: "grid", x1: padL, x2: W - padR, y1: y(t), y2: y(t) }));
    const label = svg("text", { x: padL - 6, y: y(t) + 4, "text-anchor": "end" });
    label.textContent = measure === "share" ? pct(t) : compact(t);
    s.append(label);
  }
  const labelEvery = Math.ceil(quarters.length / Math.floor(plotW / 64));
  const tip = el("div", { class: "tooltip", hidden: "" });

  quarters.forEach((q, i) => {
    const cx = padL + band * i + band / 2;
    const counts = byQ.get(q);
    const total = totals[i];
    let acc = 0;
    const segs = orgs.filter((o) => counts.get(o));
    segs.forEach((o, j) => {
      const n = counts.get(o);
      const v = measure === "share" ? n / total : n;
      const y0 = y(acc), y1 = y(acc + v);
      acc += v;
      const gap = j < segs.length - 1 ? 2 : 0; // surface gap between segments
      const h = Math.max(y0 - y1 - gap, 0.5);
      const top = j === segs.length - 1;
      const attrs = { class: "seg", x: cx - barW / 2, y: y1 + (top ? 0 : gap), width: barW, height: h,
        fill: orgColor.get(o), tabindex: "0" };
      const r = top ? roundTop(cx - barW / 2, y1, barW, h, Math.min(4, h)) : null;
      const mark = r ? svg("path", { ...attrs, d: r }) : svg("rect", attrs);
      if (r) mark.setAttribute("class", "seg");
      const show = (ev) => showTip(tip, box, ev, q, counts, total, o, q === partialQ);
      mark.addEventListener("pointermove", show);
      mark.addEventListener("focus", show);
      mark.addEventListener("pointerleave", () => (tip.hidden = true));
      mark.addEventListener("blur", () => (tip.hidden = true));
      s.append(mark);
    });
    if ((quarters.length - 1 - i) % labelEvery === 0) { // anchored on the latest quarter
      const t = svg("text", { x: cx, y: H - 8, "text-anchor": "middle" });
      t.textContent = q === partialQ ? `${q}*` : q;
      s.append(t);
    }
  });
  s.append(svg("line", { class: "base", x1: padL, x2: W - padR, y1: y(0), y2: y(0) }));
  box.append(s, tip);
  if (partialQ && quarters.includes(partialQ)) box.append(el("p", { class: "muted" }, `* ${partialQ} so far.`));

  // Table view.
  const head = ["Quarter", ...orgs, "Total"];
  const rows = quarters.map((q, i) => [q, ...orgs.map((o) => {
    const n = byQ.get(q).get(o) || 0;
    return measure === "share" ? pct(n / totals[i]) : fmt.format(n);
  }), fmt.format(totals[i])]);
  $("chart-table").replaceChildren(table(head, rows, head.map((_, i) => i).slice(1)));
}

function roundTop(x, y, w, h, r) {
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

function showTip(tip, box, ev, q, counts, total, active, partial) {
  tip.replaceChildren(el("div", { class: "when" }, `${q}${partial ? " (so far)" : ""} · ${fmt.format(total)} total`));
  for (const o of legendOrgs) {
    const n = counts.get(o);
    if (!n) continue;
    const row = el("div", { class: `row${o === active ? " active" : ""}` });
    row.append(el("span", { class: "key", style: `background:${orgColor.get(o)}` }),
      el("strong", {}, `${pct(n / total)}`), el("span", {}, ` ${fmt.format(n)} · ${o}`));
    tip.append(row);
  }
  tip.hidden = false;
  const b = box.getBoundingClientRect();
  let px, py;
  if (ev.clientX !== undefined && ev.type === "pointermove") {
    px = ev.clientX - b.left; py = ev.clientY - b.top;
  } else {
    const r = ev.target.getBoundingClientRect();
    px = r.right - b.left; py = r.top - b.top;
  }
  const tw = tip.offsetWidth;
  tip.style.left = `${px + 14 + tw > b.width ? px - tw - 14 : px + 14}px`;
  tip.style.top = `${Math.max(0, py - 20)}px`;
}

function niceMax(v) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}
function ticks(max, measure) {
  if (measure === "share") return [0, 0.25, 0.5, 0.75, 1];
  return [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);
}
function compact(v) {
  return v >= 10000 ? `${fmt.format(v / 1000)}K` : fmt.format(v);
}

function renderConcentration() {
  const idx = new Map(data.concentration.map(([repo, action, ...rest]) => [`${repo}|${action}`, rest]));
  const repos = [ALL, ...data.repos].filter((r) => idx.has(`${r}|review`) || idx.has(`${r}|merge`));
  repos.sort((a, b) => (a === ALL ? -1 : b === ALL ? 1 : (idx.get(`${b}|review`)?.[0] || 0) - (idx.get(`${a}|review`)?.[0] || 0)));
  const cell = (r, a, k) => {
    const v = idx.get(`${r}|${a}`);
    if (!v) return "–";
    const [total, people, p50, p80, top] = v;
    return [fmt.format(total), fmt.format(people), String(p50), String(p80), pct(top)][k];
  };
  const head = ["Spec", "Reviews", "Reviewers", "People for 50%", "Top reviewer's share", "Merges", "Mergers", "People for 50%"];
  const rows = repos.map((r) => [specName(r), cell(r, "review", 0), cell(r, "review", 1), cell(r, "review", 2),
    cell(r, "review", 4), cell(r, "merge", 0), cell(r, "merge", 1), cell(r, "merge", 2)]);
  $("concentration").replaceChildren(table(head, rows, [1, 2, 3, 4, 5, 6, 7]));
}

function renderPeople(repo, action) {
  $("people-title").textContent = `Most active, last 12 months: ${ACTION_LABELS[action].toLowerCase()}${repo === ALL ? "" : ` (${specName(repo)})`}`;
  const by = new Map();
  for (const [r, login, org, a, n] of data.people) {
    if (a !== action || (repo !== ALL && r !== repo)) continue;
    const p = by.get(login) || { login, org, n: 0 };
    p.n += n;
    by.set(login, p);
  }
  const top = [...by.values()].sort((a, b) => b.n - a.n).slice(0, 15);
  const total = [...by.values()].reduce((s, p) => s + p.n, 0);
  if (!top.length) {
    $("people").replaceChildren(el("p", { class: "empty" }, "No activity in this window."));
    return;
  }
  const rows = top.map((p) => {
    const a = el("a", { href: `https://github.com/${encodeURIComponent(p.login)}` }, p.login);
    return [a, p.org, fmt.format(p.n), pct(p.n / total)];
  });
  $("people").replaceChildren(table(["Account", "Organization", ACTION_LABELS[action], "Share"], rows, [2, 3]));
}

function renderResponse(repo) {
  const rows = new Map(); // quarter -> {pr, issue}
  for (const [r, kind, q, opened, unanswered, median] of data.response) {
    if (r !== repo) continue;
    if (!rows.has(q)) rows.set(q, {});
    rows.get(q)[kind] = { opened, unanswered, median };
  }
  const qs = [...rows.keys()].sort().slice(-8).reverse();
  const c = (v, k) => (v ? (k === "median" ? (v.median === null ? "–" : v.median.toFixed(1)) : fmt.format(v[k])) : "–");
  const body = qs.map((q) => {
    const { pr, issue } = rows.get(q);
    return [q.replace("-", " "), c(pr, "opened"), c(pr, "median"), c(pr, "unanswered"),
      c(issue, "opened"), c(issue, "median"), c(issue, "unanswered")];
  });
  if (!body.length) {
    $("response").replaceChildren(el("p", { class: "empty" }, "No data for this selection."));
    return;
  }
  $("response").replaceChildren(table(
    ["Opened in", "PRs", "Median days", "Unanswered", "Issues", "Median days", "Unanswered"], body, [1, 2, 3, 4, 5, 6]));
}

fetch(dataUrl)
  .then((r) => {
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  })
  .then(
    (d) => {
      data = d;
      setup();
      render();
      let last = $("chart").clientWidth;
      new ResizeObserver(() => {
        const w = $("chart").clientWidth;
        if (w !== last) {
          last = w;
          render();
        }
      }).observe($("chart"));
    },
    (e) => {
      $("chart").replaceChildren(el("p", { class: "empty" },
        `No summary data yet (${e.message}). Run the pipeline in README.md to create summaries/maintenance.json.`));
    });
