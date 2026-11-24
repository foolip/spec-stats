"use client";

// The whole page but the footer: header, view tabs, filters and the view's
// sections. The page is prerendered with the default state's figures (the
// charts as empty boxes of their final size); once hydrated, the state is
// read from the URL, and once the data has loaded every figure is computed
// from it in memory.

import { useEffect, useMemo, useState, useSyncExternalStore, type MouseEvent } from "react";
import { Calendar, dayName, formatChange, formatCount, formatPercent, mediumDate, standardDate } from "@/lib/dates.ts";
import { fromRaw, type Data, type RawData, type Repo } from "@/lib/data.ts";
import { computeModel, type Bar, type Model, type Series } from "@/lib/model.ts";
import { PERIOD_LABELS, resolveBin } from "@/lib/bins.ts";
import {
  BINS,
  PRESETS,
  PRESET_LABELS,
  VIEWS,
  formatUrl,
  parseUrl,
  presetOf,
  presetRange,
  type Bin,
  type State,
} from "@/lib/state.ts";
import { SITE_NAME, TEXTS, pageTitle } from "@/lib/texts.ts";
import StackedArea from "./StackedArea.tsx";
import StackedBars, { barFlag } from "./StackedBars.tsx";
import { Legend } from "./chart.tsx";

const BASE = process.env.NEXT_PUBLIC_SITE_BASE ?? "";

const loads = new Map<string, Promise<Data>>();
function loadData(url: string): Promise<Data> {
  let p = loads.get(url);
  if (!p) {
    p = fetch(url).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      return fromRaw((await r.json()) as RawData);
    });
    loads.set(url, p);
  }
  return p;
}

const URL_CHANGE = "specstats:urlchange";
function currentUrl() {
  return location.pathname + location.search;
}
function subscribeUrl(onChange: () => void) {
  addEventListener("popstate", onChange);
  addEventListener(URL_CHANGE, onChange);
  return () => {
    removeEventListener("popstate", onChange);
    removeEventListener(URL_CHANGE, onChange);
  };
}
/** Changing a control replaces the history entry; changing view adds one. */
function setUrl(url: string, push: boolean) {
  if (push) history.pushState(null, "", url);
  else history.replaceState(history.state, "", url);
  dispatchEvent(new Event(URL_CHANGE));
}

interface Props {
  win: { from: string; to: string };
  repos: Repo[];
  initial: State;
  model: Model;
  dataUrl: string;
}

function sameState(a: State, b: State) {
  return a.view === b.view && a.spec === b.spec && a.from === b.from && a.to === b.to && a.bin === b.bin;
}

export default function Dashboard({ win, repos, initial, model: prerendered, dataUrl }: Props) {
  const cal = useMemo(() => new Calendar(win.from), [win.from]);
  const specNames = useMemo(() => repos.map((r) => r.name), [repos]);
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The URL is the state: read it on every change, and the prerendered state's URL on the server
  // and while hydrating.
  const serverUrl = useMemo(() => formatUrl(initial, win, BASE), [initial, win]);
  const url = useSyncExternalStore(subscribeUrl, currentUrl, () => serverUrl);
  const state = useMemo(() => {
    const u = new URL(url, "http://x");
    return parseUrl(u.pathname, u.search, win, specNames, BASE);
  }, [url, win, specNames]);

  // Drop unknown or invalid parameters, and give the site's root its view's path.
  // Read the location itself: while hydrating, `state` is still the prerendered one.
  useEffect(() => {
    const canonical = formatUrl(parseUrl(location.pathname, location.search, win, specNames, BASE), win, BASE);
    if (canonical !== currentUrl()) setUrl(canonical, false);
  }, [url, win, specNames]);

  useEffect(() => {
    loadData(dataUrl).then(setData, (e: Error) => setError(`The data couldn’t be loaded (${e.message}).`));
  }, [dataUrl]);

  const model = useMemo(
    () => (data ? computeModel(data, state, { daily: true }) : sameState(state, initial) ? prerendered : null),
    [data, state, initial, prerendered],
  );

  // The prerendered figures stay hidden while they're not the URL's.
  useEffect(() => {
    if (model) document.documentElement.removeAttribute("data-pending");
    else document.documentElement.setAttribute("data-pending", "");
  }, [model]);

  const standard = state.spec ? (repos.find((r) => r.name === state.spec)?.standard ?? null) : null;
  useEffect(() => {
    document.title = pageTitle(state.view, standard);
  }, [state.view, standard]);

  const update = (change: Partial<State>, push = false) => {
    const next = { ...state, ...change };
    setUrl(formatUrl(next, win, BASE), push);
  };

  const preset = presetOf(win, state.from, state.to);
  const texts = TEXTS[state.view];
  const shown = model ?? prerendered;
  const end = cal.day(win.to);

  const followLink = (change: Partial<State>, push: boolean) => (e: MouseEvent<HTMLAnchorElement>) => {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    update(change, push);
  };

  return (
    <>
      <header className="head">
        <h1>{standard ?? "WHATWG"}</h1>
        <p className="subtitle">
          {SITE_NAME} — Last Updated {standardDate(cal.date(end))}
        </p>
        <a className="logo" href={`${BASE}/`} aria-label="Living Statistics home">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={`${BASE}/favicon.svg`} alt="" width={72} height={72} />
        </a>
      </header>

      <nav aria-label="Views">
        <ul className="tabs">
          {VIEWS.map((v) => (
            <li key={v}>
              <a
                href={formatUrl({ ...state, view: v }, win, BASE)}
                aria-current={v === state.view ? "page" : undefined}
                onClick={followLink({ view: v }, true)}
              >
                {TEXTS[v].tab}
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <p className="question">{texts.question}</p>

      <form className="filters island" aria-label="Filters" onSubmit={(e) => e.preventDefault()}>
        <label>
          Spec
          <select name="spec" value={state.spec ?? ""} onChange={(e) => update({ spec: e.target.value || null })}>
            <option value="">All specs</option>
            {repos.map((r) => (
              <option key={r.name} value={r.name}>
                {r.standard}
              </option>
            ))}
          </select>
        </label>
        <label>
          Period
          <select
            name="period"
            value={preset ?? "custom"}
            onChange={(e) => {
              if (e.target.value !== "custom") update(presetRange(win, e.target.value as (typeof PRESETS)[number]));
            }}
          >
            {PRESETS.map((p) => (
              <option key={p} value={p}>
                {PRESET_LABELS[p]}
              </option>
            ))}
            {preset === null && <option value="custom">Custom range</option>}
          </select>
        </label>
        <label>
          Per
          <select name="bin" value={state.bin} onChange={(e) => update({ bin: e.target.value as Bin })}>
            {BINS.map((b) => (
              <option key={b} value={b}>
                {b === "auto" ? `Auto (${PERIOD_LABELS[resolveBin(cal, state.from, state.to, "auto")].toLowerCase()})` : PERIOD_LABELS[b]}
              </option>
            ))}
          </select>
        </label>
      </form>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <main className="island">
        <Tiles cal={cal} model={shown} />
        <OpenPanel cal={cal} model={shown} ready={data !== null && model !== null} />
        <BarsPanel
          cal={cal}
          model={shown}
          heading={texts.openedHeading}
          about={`Each of the ${texts.noun} opened in a period, by how long it took to close it. Periods in the data’s last 7 days are provisional: their ${texts.noun} may still be closed within a week.`}
          series={shown.openedSeries}
          bars={shown.opened}
          ready={data !== null && model !== null}
        />
        <BarsPanel
          cal={cal}
          model={shown}
          heading={texts.closedHeading}
          about={
            state.view === "reviews"
              ? "PRs merged in a period, by the time from creation to merge, and PRs closed without merging."
              : "Issues closed in a period, by the time from creation to the last close."
          }
          series={shown.closedSeries}
          bars={shown.closed}
          ready={data !== null && model !== null}
        />
        {shown.spec === null && (
          <BySpec
            model={shown}
            linkFor={(name) => formatUrl({ ...state, spec: name }, win, BASE)}
            onSelect={(name) => followLink({ spec: name }, false)}
          />
        )}
      </main>
    </>
  );
}

function Tiles({ cal, model }: { cal: Calendar; model: Model }) {
  const texts = TEXTS[model.view];
  const { tiles, from, to } = model;
  return (
    <dl className="tiles">
      <div className="tile">
        <dt>Open on {mediumDate(cal.date(to))}</dt>
        <dd>{formatCount(tiles.open)}</dd>
      </div>
      <div className="tile">
        <dt>Change since {mediumDate(cal.date(from - 1))}</dt>
        <dd>
          {formatChange(tiles.change)}
          <span className="note">from {formatCount(tiles.openBefore)} open</span>
        </dd>
      </div>
      <div className="tile">
        <dt>
          {texts.closedTile} {mediumDate(cal.date(from))} to {mediumDate(cal.date(to))}
        </dt>
        <dd>
          {formatCount(tiles.closed)}
          <span className="note">
            {formatCount(tiles.opened)} {texts.noun} opened
          </span>
        </dd>
      </div>
    </dl>
  );
}

function OpenPanel({ cal, model, ready }: { cal: Calendar; model: Model; ready: boolean }) {
  const texts = TEXTS[model.view];
  const reversed = [...model.cohorts].reverse();
  return (
    <section className="panel" aria-labelledby="open-heading">
      <h2 id="open-heading">{texts.openHeading}</h2>
      <p className="about">
        {model.view === "reviews" ? "Open PRs, drafts included," : "Open issues"} at the end of each {model.period}, stacked by the
        year they were opened, oldest at the bottom.
      </p>
      <Legend series={model.cohorts} />
      <StackedArea cal={cal} model={ready ? model : { ...model, daily: undefined }} label={texts.openHeading} />
      <details className="data">
        <summary>Table</summary>
        <div className="scroll">
          <table className="numbers">
            <thead>
              <tr>
                <th scope="col">Open at the end of</th>
                {reversed.map((s) => (
                  <th scope="col" key={s.key}>
                    {s.label}
                  </th>
                ))}
                <th scope="col">Total</th>
              </tr>
            </thead>
            <tbody>
              {model.openPoints.map((p) => (
                <tr key={p.day}>
                  <th scope="row">{dayName(cal.date(p.day))}</th>
                  {[...p.values].reverse().map((v, i) => (
                    <td key={i}>{formatCount(v)}</td>
                  ))}
                  <td>{formatCount(p.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}

function BarsPanel({
  cal,
  model,
  heading,
  about,
  series,
  bars,
  ready,
}: {
  cal: Calendar;
  model: Model;
  heading: string;
  about: string;
  series: Series[];
  bars: Bar[];
  ready: boolean;
}) {
  const reversed = [...series].reverse();
  const totals = series.map((_, i) => bars.reduce((a, b) => a + b.values[i], 0));
  const total = totals.reduce((a, b) => a + b, 0);
  const id = heading.toLowerCase().replace(/[^a-z]+/g, "-");
  return (
    <section className="panel" aria-labelledby={id}>
      <h2 id={id}>{heading}</h2>
      <p className="about">{about}</p>
      <Legend series={series} />
      <StackedBars cal={cal} from={model.from} to={model.to} series={series} bars={bars} label={heading} ready={ready} />
      <details className="data">
        <summary>Table</summary>
        <div className="scroll">
          <table className="numbers">
            <thead>
              <tr>
                <th scope="col">{model.period[0].toUpperCase() + model.period.slice(1)}</th>
                {reversed.map((s) => (
                  <th scope="col" key={s.key}>
                    {s.label}
                  </th>
                ))}
                <th scope="col">Total</th>
              </tr>
            </thead>
            <tbody>
              {bars.map((b) => (
                <tr key={b.start}>
                  <th scope="row">
                    {b.name}
                    {barFlag(b) && <span className="flag"> ({barFlag(b)})</span>}
                  </th>
                  {[...b.values].reverse().map((v, i) => (
                    <td key={i}>{formatCount(v)}</td>
                  ))}
                  <td>{formatCount(b.total)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <th scope="row">All</th>
                {[...totals].reverse().map((v, i) => (
                  <td key={i}>
                    {formatCount(v)} <span className="flag">{formatPercent(v, total)}</span>
                  </td>
                ))}
                <td>{formatCount(total)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </details>
    </section>
  );
}

function BySpec({
  model,
  linkFor,
  onSelect,
}: {
  model: Model;
  linkFor: (name: string) => string;
  onSelect: (name: string) => (e: MouseEvent<HTMLAnchorElement>) => void;
}) {
  const texts = TEXTS[model.view];
  return (
    <section className="panel" aria-labelledby="by-spec-heading">
      <h2 id="by-spec-heading">By spec</h2>
      <p className="about">Choose a spec to see its charts.</p>
      <div className="scroll" style={{ maxHeight: "none" }}>
        <table className="numbers">
          <thead>
            <tr>
              <th scope="col">Spec</th>
              <th scope="col">Open</th>
              <th scope="col">Change</th>
              <th scope="col">Opened</th>
              <th scope="col">{texts.closedColumn}</th>
            </tr>
          </thead>
          <tbody>
            {model.bySpec.map((r) => (
              <tr key={r.name}>
                <th scope="row">
                  <a href={linkFor(r.name)} onClick={onSelect(r.name)}>
                    {r.standard}
                  </a>
                </th>
                <td>{formatCount(r.open)}</td>
                <td>{formatChange(r.change)}</td>
                <td>{formatCount(r.opened)}</td>
                <td>{formatCount(r.closed)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
