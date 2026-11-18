<script lang="ts">
  // A stacked area chart of daily values, with a crosshair and tooltip
  // (pointer and keyboard) and direct labels at the right edge.
  import { scaleLinear, scaleUtc } from "d3-scale";
  import { area as d3area, line as d3line } from "d3-shape";
  import { dateOf, parseDate } from "../lib/data.ts";
  import { longDate, num } from "../lib/format.ts";

  export interface Layer {
    label: string;
    /** One value per day of the window. */
    values: Int32Array;
    /** A CSS colour, e.g. var(--series-1). */
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
    label: string;
    height?: number;
  }
  let { from, start, end, layers, label, height = 320 }: Props = $props();

  let width = $state(720);
  let hover = $state<number | null>(null);

  const M = $derived({ top: 12, right: width < 520 ? 84 : 112, bottom: 28, left: 40 });
  const days = $derived(Array.from({ length: end - start + 1 }, (_, k) => start + k));
  const tops = $derived(
    layers.map((_, l) => days.map((d) => layers.slice(0, l + 1).reduce((s, layer) => s + layer.values[d], 0))),
  );
  const totals = $derived(tops.at(-1) ?? []);
  const x = $derived(
    scaleUtc()
      .domain([parseDate(dateOf(from, start)), parseDate(dateOf(from, end))])
      .range([M.left, Math.max(M.left + 1, width - M.right)]),
  );
  const y = $derived(
    scaleLinear()
      .domain([0, Math.max(1, ...totals)])
      .nice(5)
      .range([height - M.bottom, M.top]),
  );
  const xAt = (d: number) => x(parseDate(dateOf(from, d)));
  const paths = $derived(
    layers.map((_, l) =>
      d3area<number>()
        .x((_, k) => xAt(days[k]))
        .y0((_, k) => y(l === 0 ? 0 : tops[l - 1][k]))
        .y1((_, k) => y(tops[l][k]))(days) ?? "",
    ),
  );
  const outline = $derived(
    d3line<number>()
      .x((_, k) => xAt(days[k]))
      .y((t) => y(t))(totals) ?? "",
  );
  const xTicks = $derived(x.ticks(Math.max(2, Math.floor(width / 110))));
  const yTicks = $derived(y.ticks(5));
  const tickFormat = $derived(x.tickFormat());

  // Direct labels: each layer's last value, at the middle of its band,
  // nudged apart so they don't overlap.
  const endLabels = $derived.by(() => {
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
    const d = Math.round((t - parseDate(from)) / 86_400_000);
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

  /** What a screen reader hears for a day: "17 Nov 2026: 291 ready, 34 drafts". */
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
        <text x={M.left - 8} y={y(t)} dy="0.32em" text-anchor="end">{num(t)}</text>
      {/each}
    </g>
    {#each paths as d, l (l)}
      <path {d} fill={layers[l].color} class="band" />
    {/each}
    <path d={outline} class="outline" />
    <g class="axis">
      <line x1={M.left} x2={width - M.right} y1={height - M.bottom} y2={height - M.bottom} />
      {#each xTicks as t (t.getTime())}
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
      <circle class="dot" cx={xAt(hover!)} cy={y(totals[hoverK])} r="4" />
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
          {#each [...layers].reverse() as layer (layer.label)}
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
