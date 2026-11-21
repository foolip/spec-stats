<script lang="ts">
  // Stacked bars, one per calendar period, on the same time axis and
  // margins as StackedArea, so the two line up when shown one above the
  // other. A tooltip per bar (pointer and keyboard).
  import { scaleLinear, scaleUtc } from "d3-scale";
  import { margins } from "../lib/chart.ts";
  import { dateOf, parseDate } from "../lib/data.ts";
  import { longDate, num } from "../lib/format.ts";
  import { capitalized } from "../lib/texts.ts";
  import type { Period } from "../lib/bins.ts";

  export interface BarLayer {
    label: string;
    /** One value per period. */
    values: number[];
    /** A CSS color. */
    color: string;
  }

  interface Props {
    from: string;
    /** First and last day of the axis, inclusive, as in StackedArea. */
    start: number;
    end: number;
    periods: Period[];
    /** A period's name for the tooltip, e.g. "2026-W47". */
    name: (p: Period) => string;
    /** Bottom layer first. */
    layers: BarLayer[];
    label: string;
    /** What the bars count, for the totals: "merged". */
    done: string;
    height?: number;
    /** The width to draw at until it's measured. */
    width?: number;
  }
  let { from, start, end, periods, name, layers, label, done, height = 220, width: initialWidth = 720 }: Props = $props();

  // Only the first width: bind:clientWidth keeps it up to date.
  // svelte-ignore state_referenced_locally
  let width = $state(initialWidth);

  let hover = $state<number | null>(null);

  const M = $derived(margins(width));
  const dayX = (d: number) => x(parseDate(dateOf(from, d)));
  const x = $derived(
    scaleUtc()
      .domain([parseDate(dateOf(from, start)), parseDate(dateOf(from, end + 1))])
      .range([M.left, Math.max(M.left + 1, width - M.right)]),
  );
  const totals = $derived(periods.map((_, j) => layers.reduce((s, l) => s + l.values[j], 0)));
  const y = $derived(
    scaleLinear()
      .domain([0, Math.max(1, ...totals)])
      .nice(4)
      .range([height - M.bottom, M.top]),
  );
  const xTicks = $derived(x.ticks(Math.max(3, Math.floor(width / 110))));
  const yTicks = $derived(y.ticks(4).filter((t) => Number.isInteger(t)));
  const tickFormat = $derived(x.tickFormat());

  const GAP = 2;
  /** Each bar's segments, bottom first; the top one gets rounded corners.
   * The gap between bars narrows, then goes, for bars only a few pixels
   * wide (days over years), so they don't vanish into it. */
  const bars = $derived(
    periods.map((p, j) => {
      const slot = dayX(p.end + 1) - dayX(p.start);
      const gap = slot >= 6 ? GAP : slot >= 3 ? 1 : 0;
      const x0 = dayX(p.start) + gap / 2;
      const x1 = Math.max(x0 + 0.5, dayX(p.end + 1) - gap / 2);
      let base = 0;
      const segs: { d: string; color: string }[] = [];
      const nonzero = layers.map((l, k) => [l, k] as const).filter(([l]) => l.values[j] > 0);
      nonzero.forEach(([l], n) => {
        const yb = y(base) - (n ? GAP : 0);
        const yt = Math.min(y(base + l.values[j]), yb - 1);
        const r = n === nonzero.length - 1 ? Math.min(3, (x1 - x0) / 2, (yb - yt) / 2) : 0;
        segs.push({
          d: `M${x0},${yb}V${yt + r}q0,${-r} ${r},${-r}H${x1 - r}q${r},0 ${r},${r}V${yb}Z`,
          color: l.color,
        });
        base += l.values[j];
      });
      return { x0: dayX(p.start), x1: dayX(p.end + 1), segs, partial: p.partial };
    }),
  );

  function onPointer(e: PointerEvent) {
    const rect = (e.currentTarget as SVGElement).getBoundingClientRect();
    const px = e.clientX - rect.left;
    const j = bars.findIndex((b) => px >= b.x0 && px < b.x1);
    hover = j === -1 ? null : j;
  }

  function onKey(e: KeyboardEvent) {
    const cur = hover ?? periods.length - 1;
    const next =
      e.key === "ArrowLeft" ? cur - 1
      : e.key === "ArrowRight" ? cur + 1
      : e.key === "Home" ? 0
      : e.key === "End" ? periods.length - 1
      : null;
    if (next === null) return;
    e.preventDefault();
    hover = Math.min(periods.length - 1, Math.max(0, next));
  }

  function dates(p: Period): string {
    return p.start === p.end
      ? longDate(dateOf(from, p.start))
      : `${longDate(dateOf(from, p.start))} – ${longDate(dateOf(from, p.end))}`;
  }

  function valueText(j: number): string {
    const p = periods[j];
    if (!p) return "";
    return `${name(p)}${p.partial ? " (partial)" : ""}: ${num(totals[j])} ${done}; ${[...layers]
      .reverse()
      .map((l) => `${num(l.values[j])} ${l.label}`)
      .join(", ")}`;
  }
  const descId = `bars-${Math.random().toString(36).slice(2)}`;
</script>

<div class="chart" bind:clientWidth={width}>
  <p id={descId} class="visually-hidden">Use the left and right arrow keys to move through the bars; Home and End go to the first and last.</p>
  <svg
    {width}
    {height}
    role="slider"
    aria-label={label}
    aria-valuemin={0}
    aria-valuemax={Math.max(0, periods.length - 1)}
    aria-valuenow={hover ?? periods.length - 1}
    aria-valuetext={valueText(hover ?? periods.length - 1)}
    aria-describedby={descId}
    tabindex="0"
    onpointermove={onPointer}
    onpointerleave={() => (hover = null)}
    onfocus={() => (hover ??= periods.length - 1)}
    onblur={() => (hover = null)}
    onkeydown={onKey}
  >
    {#each bars as b, j (j)}
      {#if b.partial}
        <rect class="partial" x={b.x0} y={M.top} width={b.x1 - b.x0} height={height - M.bottom - M.top} />
      {/if}
    {/each}
    <g class="grid">
      {#each yTicks as t (t)}
        <line x1={M.left} x2={width - M.right} y1={y(t)} y2={y(t)} />
        <text x={M.left - 8} y={y(t)} dy="0.32em" text-anchor="end">{num(t)}</text>
      {/each}
    </g>
    {#each bars as b, j (j)}
      <g class="bar" class:hover={hover === j}>
        {#each b.segs as s, k (k)}
          <path d={s.d} fill={s.color} />
        {/each}
      </g>
    {/each}
    <g class="axis">
      <line x1={M.left} x2={width - M.right} y1={height - M.bottom} y2={height - M.bottom} />
      {#each xTicks as t (t.getTime())}
        <text x={x(t)} y={height - M.bottom + 18} text-anchor="middle">{tickFormat(t)}</text>
      {/each}
    </g>
  </svg>
  {#if hover !== null && periods[hover]}
    {@const p = periods[hover]}
    <div class="tooltip" role="status" style:left="{Math.min(bars[hover].x1, width - 220)}px" style:top="{M.top}px">
      <div class="tt-date">{name(p)}</div>
      <div class="tt-sub">{dates(p)}{p.partial ? " (partial)" : ""}</div>
      <table>
        <tbody>
          {#each [...layers].reverse() as layer (layer.label)}
            <tr>
              <th scope="row"><span class="swatch" style:background={layer.color}></span>{layer.label}</th>
              <td>{num(layer.values[hover])}</td>
            </tr>
          {/each}
          <tr class="total"><th scope="row">{capitalized(done)}</th><td>{num(totals[hover])}</td></tr>
        </tbody>
      </table>
    </div>
  {/if}
</div>
