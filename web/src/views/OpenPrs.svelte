<script lang="ts">
  import RangePicker from "../components/RangePicker.svelte";
  import RepoPicker from "../components/RepoPicker.svelte";
  import StackedArea, { type Layer } from "../components/StackedArea.svelte";
  import StackedBars, { type BarLayer } from "../components/StackedBars.svelte";
  import { margins } from "../lib/chart.ts";
  import { dateOf, type Data } from "../lib/data.ts";
  import { longDate, num, signed } from "../lib/format.ts";
  import { BAND_LABELS, chooseBin, mergesByPeriod, periodName, periods } from "../lib/merges.ts";
  import { openByGroup, openByRepo, total, yearCohorts } from "../lib/openprs.ts";
  import { fixed, rangeDays, selectedRepos, serialize, type Context, type State } from "../lib/url.ts";

  interface Props {
    data: Data;
    state: State;
    ctx: Context;
    navigate: (next: State) => void;
  }
  let { data, state: view, ctx, navigate }: Props = $props();

  const byRepo = $derived(openByRepo(data));
  const repos = $derived(selectedRepos(view.repo, data.repos.name));
  const series = $derived(total(byRepo, repos, data.days));
  const [start, end] = $derived(rangeDays(view.range, ctx));
  const drafts = $derived(view.drafts === "include");

  // Open PRs by the year they were opened, oldest at the bottom.
  const cohorts = $derived(yearCohorts(data));
  const byCohort = $derived(openByGroup(data, cohorts.of, cohorts.labels.length));
  const layers: Layer[] = $derived(
    cohorts.labels.map((label, g) => {
      const values = new Int32Array(data.days);
      for (const r of repos) {
        const s = byCohort[r][g];
        for (let d = 0; d < data.days; d++) values[d] += s.ready[d] + (drafts ? s.draft[d] : 0);
      }
      return { label, values, color: `var(--cohort-${g})` };
    }),
  );

  // PRs merged per calendar period: the smallest period whose bars stay
  // at least 8 px wide (ISO weeks for a year or less at most widths).
  let barsWidth = $state(720);
  const plotWidth = $derived.by(() => {
    const m = margins(barsWidth);
    return barsWidth - m.left - m.right;
  });
  const bin = $derived(chooseBin(data.from, start, end, plotWidth));
  const mergePeriods = $derived(periods(data.from, start, end, bin));
  const mergeCounts = $derived(mergesByPeriod(data, repos, mergePeriods));
  // Fastest first, for the legend and the table; stacked the other way,
  // so the slowest is at the bottom and the fastest (lightest) on top, as
  // the open PRs' newest layer is.
  const mergeBands: BarLayer[] = $derived(
    BAND_LABELS.map((label, k) => ({ label, values: mergeCounts.map((c) => c[k]), color: `var(--age-${k})` })),
  );
  const mergeLayers = $derived([...mergeBands].reverse());
  const merged = $derived(mergeCounts.reduce((s, c) => s + c.reduce((a, b) => a + b, 0), 0));
  const UNIT = { week: "ISO week", month: "month", quarter: "quarter" } as const;

  const open = (s: { ready: Int32Array; draft: Int32Array }, d: number) => s.ready[d] + (drafts ? s.draft[d] : 0);
  const now = $derived(open(series, end));
  const change = $derived(now - open(series, start));

  const rows = $derived(
    repos
      .map((r) => ({
        r,
        standard: data.repos.standard[r],
        name: data.repos.name[r],
        open: open(byRepo[r], end),
        draft: byRepo[r].draft[end],
        change: open(byRepo[r], end) - open(byRepo[r], start),
      }))
      .sort((a, b) => b.open - a.open || a.standard.localeCompare(b.standard)),
  );
  const maxOpen = $derived(Math.max(1, ...rows.map((r) => r.open)));

  // Month ends in the range, for the chart's table view.
  const monthly = $derived.by(() => {
    const out: { date: string; values: number[]; total: number; draft: number }[] = [];
    for (let d = start; d <= end; d++) {
      const date = dateOf(data.from, d);
      const next = dateOf(data.from, d + 1);
      if (d === end || next.slice(0, 7) !== date.slice(0, 7)) {
        const values = layers.map((l) => l.values[d]);
        out.push({ date, values, total: values.reduce((a, b) => a + b, 0), draft: series.draft[d] });
      }
    }
    return out.reverse();
  });

  // Copy feedback: the label swaps in place (both labels share one grid
  // cell, so the button keeps its width), and a live region announces it.
  let copied = $state(false);
  let announcement = $state("");
  let lastAnnouncement = "";
  let copiedTimer: ReturnType<typeof setTimeout> | undefined;
  function announce(message: string) {
    // VoiceOver skips a message identical to the previous one.
    announcement = message === lastAnnouncement ? `${message}\u00a0` : message;
    lastAnnouncement = announcement;
  }
  async function copyLink() {
    const url = new URL(location.href);
    url.search = serialize({ ...view, range: fixed(view.range, ctx) });
    try {
      await navigator.clipboard.writeText(url.toString());
      copied = true;
      announce("Link to this view copied");
      clearTimeout(copiedTimer);
      copiedTimer = setTimeout(() => (copied = false), 2500);
    } catch {
      prompt("Link to this view", url.toString());
    }
  }
</script>

<article class="view">
  <hgroup>
    <h1>Open pull requests</h1>
    <p class="question">How many PRs are waiting, and is the backlog growing or shrinking?</p>
  </hgroup>

  <div class="controls" role="group" aria-label="Filters">
    <RepoPicker
      names={data.repos.name}
      standards={data.repos.standard}
      repo={view.repo}
      onchange={(r) => navigate({ ...view, repo: r })}
    />
    <RangePicker range={view.range} {ctx} onchange={(r) => navigate({ ...view, range: r })} />
    <label class="check">
      <input type="checkbox" checked={drafts}
        onchange={(e) => navigate({ ...view, drafts: e.currentTarget.checked ? "include" : "exclude" })} />
      Include drafts
    </label>
    <button type="button" class="copy" title="Copy a link to this view, with its dates fixed" onclick={copyLink}>
      <span class:hidden={copied}>Copy link</span>
      <span class:hidden={!copied} aria-hidden={!copied}>Link copied</span>
    </button>
    <span class="visually-hidden" role="status">{announcement}</span>
  </div>

  <section class="tiles" aria-label="Summary">
    <div class="tile">
      <div class="tile-label">Open on {longDate(dateOf(data.from, end))}</div>
      <div class="tile-value">{num(now)}</div>
      {#if drafts}<div class="tile-note">{num(series.draft[end])} of them drafts</div>{/if}
    </div>
    <div class="tile">
      <div class="tile-label">Change since {longDate(dateOf(data.from, start))}</div>
      <div class="tile-value" class:up={change > 0} class:down={change < 0}>{signed(change)}</div>
      <div class="tile-note">from {num(open(series, start))}</div>
    </div>
    <div class="tile">
      <div class="tile-label">Merged since {longDate(dateOf(data.from, start))}</div>
      <div class="tile-value">{num(merged)}</div>
    </div>
  </section>

  <section class="panel">
    <div class="panel-head">
      <h2>Open PRs at the end of each day, by year opened</h2>
      <ul class="legend">
        {#each [...layers].reverse() as l (l.label)}
          <li><span class="swatch" style:background={l.color}></span>{l.label}</li>
        {/each}
      </ul>
    </div>
    <StackedArea from={data.from} {start} {end} {layers} label="Open PRs by year opened" />
    <details class="table-view">
      <summary>Table: month ends</summary>
      <table>
        <thead>
          <tr>
            <th scope="col">Date</th>
            {#each [...layers].reverse() as l (l.label)}<th scope="col">{l.label}</th>{/each}
            <th scope="col">Open</th>
            {#if drafts}<th scope="col">Of them drafts</th>{/if}
          </tr>
        </thead>
        <tbody>
          {#each monthly as m (m.date)}
            <tr>
              <td>{longDate(m.date)}</td>
              {#each [...m.values].reverse() as v, k (k)}<td>{num(v)}</td>{/each}
              <td>{num(m.total)}</td>
              {#if drafts}<td>{num(m.draft)}</td>{/if}
            </tr>
          {/each}
        </tbody>
      </table>
    </details>
  </section>

  <section class="panel">
    <div class="panel-head">
      <h2>PRs merged per {UNIT[bin]}, by time from ready for review to merge</h2>
      <ul class="legend">
        {#each mergeBands as l (l.label)}
          <li><span class="swatch" style:background={l.color}></span>{l.label}</li>
        {/each}
      </ul>
    </div>
    <StackedBars from={data.from} {start} {end} periods={mergePeriods} name={(p) => periodName(p, bin)}
      layers={mergeLayers} label="PRs merged per {UNIT[bin]}" bind:width={barsWidth} />
    <details class="table-view">
      <summary>Table: merges per {UNIT[bin]}</summary>
      <table>
        <thead>
          <tr>
            <th scope="col">{UNIT[bin][0].toUpperCase() + UNIT[bin].slice(1)}</th>
            {#each mergeBands as l (l.label)}<th scope="col">{l.label}</th>{/each}
            <th scope="col">Merged</th>
          </tr>
        </thead>
        <tbody>
          {#each [...mergePeriods.keys()].reverse() as j (j)}
            <tr>
              <td>{periodName(mergePeriods[j], bin)}{mergePeriods[j].partial ? " (partial)" : ""}</td>
              {#each mergeCounts[j] as c, k (k)}<td>{num(c)}</td>{/each}
              <td>{num(mergeCounts[j].reduce((a, b) => a + b, 0))}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </details>
  </section>

  <section class="panel">
    <h2>By spec</h2>
    <table class="by-spec">
      <thead>
        <tr>
          <th scope="col">Spec</th>
          <th scope="col" class="n">Open</th>
          {#if drafts}<th scope="col" class="n">Drafts</th>{/if}
          <th scope="col" class="n">Change</th>
          <th scope="col" class="bar-col"><span class="visually-hidden">Open, as a bar</span></th>
        </tr>
      </thead>
      <tbody>
        {#each rows as row (row.name)}
          <tr>
            <th scope="row">
              <button type="button" class="spec" title="Show only {row.standard}"
                onclick={() => navigate({ ...view, repo: row.name })}>{row.standard}</button>
            </th>
            <td class="n">{num(row.open)}</td>
            {#if drafts}<td class="n muted">{num(row.draft)}</td>{/if}
            <td class="n" class:up={row.change > 0} class:down={row.change < 0}>{signed(row.change)}</td>
            <td class="bar-col"><span class="bar" style:width="{(row.open / maxOpen) * 100}%"></span></td>
          </tr>
        {/each}
      </tbody>
    </table>
  </section>
</article>
