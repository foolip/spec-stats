<script lang="ts">
  // A stacked area chart of daily values, with a crosshair and tooltip
  // (pointer and keyboard) and direct labels at the right edge.
  import { scaleLinear, scaleUtc } from "d3-scale";
  import { area as d3area, curveMonotoneX, line as d3line } from "d3-shape";
  import { directLabels, margins, TICK_LENGTH } from "../lib/chart.ts";
  import { dateOf, parseDate } from "../lib/data.ts";
  import { longDate, num } from "../lib/format.ts";

  export interface Layer {
    label: string;
    /** One value per day of the window. */
    values: Int32Array;
    /** A CSS color, e.g. var(--series-1). */
    color: string;
  }

  interface Props {
    /** The window's first date: day 0. */
    from: string;
    /** First and last day shown, inclusive. */
    start: number;
    end: number;
    /** Bottom layer first. */
    layers: Layer[];
    /** The days to draw, in order: by default every day. The tooltip still
     * shows every day's values; the y-scale fits every day too, so it
     * doesn't change with the days drawn. */
    sample?: number[];
    label: string;
    height?: number;
    /** The width to draw at until it's measured. */
    width?: number;
  }
  let { from, start, end, layers, sample, label, height = 320, width: initialWidth = 720 }: Props = $props();

  // Only the first width: bind:clientWidth keeps it up to date.
  // svelte-ignore state_referenced_locally
  let width = $state(initialWidth);
  let hover = $state<number | null>(null);

  const M = $derived(margins(width));
  const days = $derived(Array.from({ length: end - start + 1 }, (_, k) => start + k));
  const tops = $derived(
    layers.map((_, l) => days.map((d) => layers.slice(0, l + 1).reduce((s, layer) => s + layer.values[d], 0))),
  );
  const totals = $derived(tops.at(-1) ?? []);
  // The axis runs from the start of the first day to the end of the last,
  // and each day's value sits at its middle, so bars of whole days
  // (StackedBars) line up with it.
  const x = $derived(
    scaleUtc()
      .domain([parseDate(dateOf(from, start)), parseDate(dateOf(from, end + 1))])
      .range([M.left, Math.max(M.left + 1, width - M.right)]),
  );
  const y = $derived(
    scaleLinear()
      .domain([0, Math.max(1, ...totals)])
      .nice(5)
      .range([height - M.bottom, M.top]),
  );
  const xAt = (d: number) => x(parseDate(dateOf(from, d)) + 43_200_000);
  /** Indexes into days of the days drawn. */
  const drawn = $derived(sample ? sample.map((d) => d - start) : days.map((_, k) => k));
  const drawnSet = $derived(new Set(drawn));
  const paths = $derived(
    layers.map((_, l) =>
      d3area<number>()
        .curve(curveMonotoneX)
        .x((k) => xAt(days[k]))
        .y0((k) => y(l === 0 ? 0 : tops[l - 1][k]))
        .y1((k) => y(tops[l][k]))(drawn) ?? "",
    ),
  );
  const outline = $derived(
    d3line<number>()
      .curve(curveMonotoneX)
      .x((k) => xAt(days[k]))
      .y((k) => y(totals[k]))(drawn) ?? "",
  );
  const xTicks = $derived(x.ticks(Math.max(3, Math.floor(width / 110))));
  const yTicks = $derived(y.ticks(5));
  const tickFormat = $derived(x.tickFormat());

  // Direct labels where they fit: each layer's last value, at the middle
  // of its band, nudged apart so they don't overlap.
  const endLabels = $derived.by(() => {
    if (!directLabels(width)) return [];
    const k = days.length - 1;
    const out = layers.map((layer, l) => {
      const lo = l === 0 ? 0 : tops[l - 1][k];
      return { label: layer.label, value: layer.values[end], y: y((lo + tops[l][k]) / 2) };
    });
    for (let i = 1; i < out.length; i++) {
      if (out[i - 1].y - out[i].y < 16) out[i].y = out[i - 1].y - 16;
    }
    return out;
  });

  const hoverK = $derived(hover === null ? null : hover - start);

  function onPointer(e: PointerEvent) {
    const rect = (e.currentTarget as SVGElement).getBoundingClientRect();
    const t = x.invert(e.clientX - rect.left).getTime();
    const d = Math.floor((t - parseDate(from)) / 86_400_000);
    hover = Math.min(end, Math.max(start, d));
  }

  function onKey(e: KeyboardEvent) {
    const step = e.shiftKey ? 30 : 1;
    const cur = hover ?? end;
    const next =
      e.key === "ArrowLeft" ? cur - step
      : e.key === "ArrowRight" ? cur + step
      : e.key === "Home" ? start
      : e.key === "End" ? end
      : null;
    if (next === null) return;
    e.preventDefault();
    hover = Math.min(end, Math.max(start, next));
  }

  /** What a screen reader hears for a day: "Nov 17, 2026: 120 2026, 45 2025". */
  function valueText(d: number): string {
    return `${longDate(dateOf(from, d))}: ${layers.map((l) => `${num(l.values[d])} ${l.label}`).join(", ")}`;
  }
  const descId = `chart-${Math.random().toString(36).slice(2)}`;
</script>

<div class="chart" bind:clientWidth={width}>
  <p id={descId} class="visually-hidden">Use the left and right arrow keys to move through the days; Shift moves 30 days, Home and End go to the first and last day.</p>
  <svg
    {width}
    {height}
    role="slider"
    aria-label={label}
    aria-valuemin={start}
    aria-valuemax={end}
    aria-valuenow={hover ?? end}
    aria-valuetext={valueText(hover ?? end)}
    aria-describedby={descId}
    tabindex="0"
    onpointermove={onPointer}
    onpointerleave={() => (hover = null)}
    onfocus={() => (hover ??= end)}
    onblur={() => (hover = null)}
    onkeydown={onKey}
  >
    <g class="grid">
      {#each yTicks as t (t)}
        <line x1={M.left} x2={width - M.right} y1={y(t)} y2={y(t)} />
        <text x={M.left - 9} y={y(t)} dy="0.32em" text-anchor="end">{num(t)}</text>
      {/each}
    </g>
    <g class="axis">
      {#each yTicks.filter((t) => t !== 0) as t (t)}
        <line x1={M.left - TICK_LENGTH} x2={M.left} y1={y(t)} y2={y(t)} />
      {/each}
    </g>
    {#each paths as d, l (l)}
      <path {d} fill={layers[l].color} class="band" />
    {/each}
    <path d={outline} class="outline" />
    <g class="axis">
      <line x1={M.left} x2={width - M.right} y1={height - M.bottom} y2={height - M.bottom} />
      {#each xTicks as t (t.getTime())}
        <line x1={x(t)} x2={x(t)} y1={height - M.bottom} y2={height - M.bottom + TICK_LENGTH} />
        <text x={x(t)} y={height - M.bottom + 18} text-anchor="middle">{tickFormat(t)}</text>
      {/each}
    </g>
    <g class="end-labels">
      {#each endLabels as e (e.label)}
        <text x={width - M.right + 8} y={e.y} dy="0.32em"><tspan class="value">{num(e.value)}</tspan> {e.label}</text>
      {/each}
    </g>
    {#if hoverK !== null}
      <line class="crosshair" x1={xAt(hover!)} x2={xAt(hover!)} y1={M.top} y2={height - M.bottom} />
      {#if drawnSet.has(hoverK)}
        <circle class="dot" cx={xAt(hover!)} cy={y(totals[hoverK])} r="4" />
      {/if}
    {/if}
  </svg>
  {#if hover !== null && hoverK !== null}
    <div
      class="tooltip"
      role="status"
      style:left="{Math.min(xAt(hover), width - 190)}px"
      style:top="{M.top}px"
    >
      <div class="tt-date">{longDate(dateOf(from, hover))}</div>
      <table>
        <tbody>
          {#each [...layers].reverse().filter((l) => layers.length <= 2 || l.values[hover!] > 0) as layer (layer.label)}
            <tr>
              <th scope="row"><span class="swatch" style:background={layer.color}></span>{layer.label}</th>
              <td>{num(layer.values[hover])}</td>
            </tr>
          {/each}
          {#if layers.length > 1}
            <tr class="total"><th scope="row">Total</th><td>{num(totals[hoverK])}</td></tr>
          {/if}
        </tbody>
      </table>
    </div>
  {/if}
</div>
