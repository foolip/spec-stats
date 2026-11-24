"use client";

// Open items over time, stacked by year opened. Drawn through the open count
// on the range's first day and at the end of each period; the tooltip gives
// every day's counts.

import { useState, type KeyboardEvent, type PointerEvent } from "react";
import { area, curveMonotoneX } from "d3-shape";
import { dayName, type Calendar } from "@/lib/dates.ts";
import type { Model } from "@/lib/model.ts";
import { AREA_HEIGHT, LABELS_MIN_WIDTH, Tooltip, XAxis, YAxis, color, keyStep, margins, useWidth, xScale, yScale } from "./chart.tsx";

export default function StackedArea({ cal, model, label }: { cal: Calendar; model: Model; label: string }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const daily = model.daily;
  const { from, to, cohorts, openPoints } = model;
  const height = AREA_HEIGHT;

  let body = null;
  if (width > 0 && daily) {
    const m = margins(width);
    const x = xScale(from, to, width);
    const max = Math.max(...daily.total);
    const y = yScale(max, height);
    const mid = (day: number) => x(day + 0.5);

    // Cumulative stacks at the points drawn.
    const stacks = openPoints.map((p) => {
      let run = 0;
      return p.values.map((v) => [run, (run += v)] as const);
    });
    const paths = cohorts.map((_, layer) =>
      area<number>()
        .x((i) => mid(openPoints[i].day))
        .y0((i) => y(stacks[i][layer][0]))
        .y1((i) => y(stacks[i][layer][1]))
        .curve(curveMonotoneX)(openPoints.map((_, i) => i)),
    );

    // Direct labels at the right, where a layer is tall enough to hold one.
    const last = stacks[stacks.length - 1];
    const lastX = mid(openPoints[openPoints.length - 1].day);
    const labels =
      width >= LABELS_MIN_WIDTH
        ? cohorts
            .map((s, layer) => ({ s, y0: y(last[layer][0]), y1: y(last[layer][1]) }))
            .filter((l) => l.y0 - l.y1 >= 6)
            .map((l) => ({ ...l, at: (l.y0 + l.y1) / 2 }))
        : [];
    // Keep labels at least 12 px apart, from the bottom up.
    for (let i = 1; i < labels.length; i++) labels[i].at = Math.min(labels[i].at, labels[i - 1].at - 12);

    const onPointer = (e: PointerEvent<SVGSVGElement>) => {
      const rect = e.currentTarget.getBoundingClientRect();
      const day = Math.floor(x.invert(e.clientX - rect.left));
      setActive(Math.min(to, Math.max(from, day)) - from);
    };
    const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
      const next = keyStep(e.key, active, to - from + 1, 7);
      if (next !== null) {
        e.preventDefault();
        setActive(next);
      } else if (e.key === "Escape") setActive(null);
    };

    const ax = active === null ? null : mid(from + active);
    body = (
      <>
        <svg
          width={width}
          height={height}
          role="img"
          aria-label={`${label}. Use the arrow keys to read each day's counts.`}
          tabIndex={0}
          onPointerMove={onPointer}
          onPointerDown={onPointer}
          onPointerLeave={() => setActive(null)}
          onKeyDown={onKey}
          onBlur={() => setActive(null)}
        >
          <YAxis max={max} width={width} height={height} />
          {paths.map((d, layer) => (
            <path key={cohorts[layer].key} d={d ?? ""} fill={color(cohorts[layer])} />
          ))}
          <XAxis cal={cal} from={from} to={to} width={width} height={height} />
          {labels.map((l) => (
            <text key={l.s.key} className="direct-label" x={lastX + 6} y={l.at} dy="0.32em">
              {l.s.label}
            </text>
          ))}
          {ax !== null && <line className="crosshair" x1={ax} x2={ax} y1={m.top} y2={height - m.bottom} />}
        </svg>
        {active !== null && ax !== null && (
          <Tooltip
            x={ax}
            width={width}
            title={`Open at the end of ${dayName(cal.date(from + active))}`}
            rows={cohorts
              .map((s, layer) => ({ label: s.label, value: daily.values[layer][active], color: color(s) }))
              .reverse()}
            total={daily.total[active]}
          />
        )}
      </>
    );
  }

  return (
    <div className="chart" ref={ref} style={{ height }}>
      {body}
    </div>
  );
}
