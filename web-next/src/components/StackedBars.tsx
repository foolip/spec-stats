"use client";

// Items per period, stacked by band, on the same time axis as the area chart.

import { useId, useState, type KeyboardEvent } from "react";
import type { Calendar } from "@/lib/dates.ts";
import type { Bar, Series } from "@/lib/model.ts";
import { BARS_HEIGHT, Tooltip, XAxis, YAxis, color, keyStep, margins, useWidth, xScale, yScale } from "./chart.tsx";

export function barFlag(bar: Bar): string | undefined {
  const flags = [];
  if (bar.partial) flags.push("partial");
  if (bar.provisional) flags.push("provisional");
  return flags.length ? flags.join(", ") : undefined;
}

export default function StackedBars({
  cal,
  from,
  to,
  series,
  bars,
  label,
  ready,
}: {
  cal: Calendar;
  from: number;
  to: number;
  series: Series[];
  bars: Bar[];
  label: string;
  ready: boolean;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const patternId = `partial${useId().replace(/[^A-Za-z0-9_-]/g, "")}`;
  const height = BARS_HEIGHT;

  let body = null;
  if (width > 0 && ready) {
    const m = margins(width);
    const x = xScale(from, to, width);
    const max = Math.max(0, ...bars.map((b) => b.total));
    const y = yScale(max, height);
    const dayWidth = x(from + 1) - x(from);
    // Bars only a few pixels wide lose the gap between them.
    const gap = dayWidth * (bars[0] ? bars[0].end - bars[0].start + 1 : 1) >= 6 ? 1 : 0;

    const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
      const next = keyStep(e.key, active, bars.length, 4);
      if (next !== null) {
        e.preventDefault();
        setActive(next);
      } else if (e.key === "Escape") setActive(null);
    };

    const a = active === null ? null : bars[active];
    body = (
      <>
        <svg
          width={width}
          height={height}
          role="img"
          aria-label={`${label}. Use the arrow keys to read each period's counts.`}
          tabIndex={0}
          onKeyDown={onKey}
          onPointerLeave={() => setActive(null)}
          onBlur={() => setActive(null)}
        >
          <defs>
            <pattern id={patternId} width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="2" height="4" fill="var(--bg)" opacity="0.55" />
            </pattern>
          </defs>
          <YAxis max={max} width={width} height={height} />
          {bars.map((b, i) => {
            const x0 = x(b.start) + gap / 2;
            const w = Math.max(0.5, x(b.end + 1) - x(b.start) - gap);
            let run = 0;
            return (
              <g key={b.start}>
                {b.values.map((v, layer) => {
                  if (!v) return null;
                  const y1 = y(run);
                  const y0 = y((run += v));
                  return <rect key={layer} x={x0} y={y0} width={w} height={y1 - y0} fill={color(series[layer])} />;
                })}
                {(b.partial || b.provisional) && b.total > 0 && (
                  <rect x={x0} y={y(b.total)} width={w} height={y(0) - y(b.total)} fill={`url(#${patternId})`} />
                )}
                <rect
                  className={i === active ? "bar-hit active" : "bar-hit"}
                  x={x(b.start)}
                  y={m.top}
                  width={x(b.end + 1) - x(b.start)}
                  height={height - m.top - m.bottom}
                  onPointerEnter={() => setActive(i)}
                  onPointerDown={() => setActive(i)}
                />
              </g>
            );
          })}
          <XAxis cal={cal} from={from} to={to} width={width} height={height} />
        </svg>
        {a && (
          <Tooltip
            x={x((a.start + a.end + 1) / 2)}
            width={width}
            title={a.name}
            flag={barFlag(a)}
            rows={series.map((s, layer) => ({ label: s.label, value: a.values[layer], color: color(s) })).reverse()}
            total={a.total}
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
