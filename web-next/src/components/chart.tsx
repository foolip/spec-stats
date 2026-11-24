"use client";

// Shared geometry and pieces for the charts, which share one time axis.

import { useEffect, useRef, useState, type ReactNode } from "react";
import { scaleLinear, scaleUtc } from "d3-scale";
import type { Calendar } from "@/lib/dates.ts";
import { formatCount } from "@/lib/dates.ts";
import type { Series } from "@/lib/model.ts";

export const AREA_HEIGHT = 260;
export const BARS_HEIGHT = 200;
/** Below this width the area chart drops its direct labels so the plot gets the room. */
export const LABELS_MIN_WIDTH = 480;

export function margins(width: number) {
  return { top: 10, right: width >= LABELS_MIN_WIDTH ? 92 : 12, bottom: 24, left: 44 };
}

/** The x scale in days: from the start of the first day to the end of the last. */
export function xScale(from: number, to: number, width: number) {
  const m = margins(width);
  return scaleLinear().domain([from, to + 1]).range([m.left, width - m.right]);
}

export function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

export function color(s: Series): string {
  return `var(${s.color})`;
}

export function XAxis({ cal, from, to, width, height }: { cal: Calendar; from: number; to: number; width: number; height: number }) {
  const m = margins(width);
  const t = scaleUtc().domain([cal.date(from), cal.date(to + 1)]).range([m.left, width - m.right]);
  const ticks = t.ticks(Math.max(2, Math.floor((width - m.left - m.right) / 80)));
  const format = t.tickFormat();
  const y = height - m.bottom;
  return (
    <g className="axis" aria-hidden="true">
      <line x1={m.left} x2={width - m.right} y1={y} y2={y} />
      {ticks.map((d) => {
        const x = t(d);
        return (
          <g key={+d} transform={`translate(${x},${y})`}>
            <line y2={5} />
            <text y={17} textAnchor="middle">
              {format(d)}
            </text>
          </g>
        );
      })}
    </g>
  );
}

export function YAxis({ max, width, height }: { max: number; width: number; height: number }) {
  const m = margins(width);
  const y = yScale(max, height);
  const ticks = y.ticks(height > 220 ? 5 : 4).filter(Number.isInteger);
  return (
    <g className="axis" aria-hidden="true">
      {ticks.map((v) => (
        <g key={v} transform={`translate(0,${y(v)})`}>
          {v !== 0 && <line className="gridline" x1={m.left} x2={width - m.right} />}
          {v !== 0 && <line x1={m.left - 5} x2={m.left} />}
          <text x={m.left - 8} dy="0.32em" textAnchor="end">
            {formatCount(v)}
          </text>
        </g>
      ))}
    </g>
  );
}

export function yScale(max: number, height: number) {
  const m = { top: 10, bottom: 24 };
  return scaleLinear()
    .domain([0, Math.max(1, max)])
    .nice(height > 220 ? 5 : 4)
    .range([height - m.bottom, m.top]);
}

export function Legend({ series }: { series: Series[] }) {
  // Top of the stack first, as the chart reads.
  return (
    <ul className="legend">
      {[...series].reverse().map((s) => (
        <li key={s.key}>
          <span className="swatch" style={{ background: color(s) }} aria-hidden="true" />
          {s.label}
        </li>
      ))}
    </ul>
  );
}

export interface TooltipRow {
  label: string;
  value: number;
  color?: string;
}

export function Tooltip({
  x,
  width,
  title,
  flag,
  rows,
  total,
}: {
  x: number;
  width: number;
  title: string;
  flag?: string;
  rows: TooltipRow[];
  total: number;
}): ReactNode {
  const tipWidth = 200;
  const left = x + 12 + tipWidth > width ? Math.max(0, x - 12 - tipWidth) : x + 12;
  return (
    <div className="tooltip" style={{ left, width: tipWidth }} role="status" aria-live="polite">
      <div className="t-title">{title}</div>
      {flag && <div className="t-flag">{flag}</div>}
      <table>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label}>
              <td>
                {r.color && <span className="swatch" style={{ background: r.color, marginRight: 6 }} aria-hidden="true" />}
                {r.label}
              </td>
              <td className="n">{formatCount(r.value)}</td>
            </tr>
          ))}
          <tr className="total">
            <td>Total</td>
            <td className="n">{formatCount(total)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

/** Arrow keys, Home and End move through `count` positions. */
export function keyStep(key: string, index: number | null, count: number, page: number): number | null {
  const i = index ?? (key === "ArrowLeft" || key === "End" ? count : -1);
  switch (key) {
    case "ArrowLeft":
      return Math.max(0, i - 1);
    case "ArrowRight":
      return Math.min(count - 1, i + 1);
    case "PageUp":
      return Math.max(0, i - page);
    case "PageDown":
      return Math.min(count - 1, i + page);
    case "Home":
      return 0;
    case "End":
      return count - 1;
    default:
      return null;
  }
}
