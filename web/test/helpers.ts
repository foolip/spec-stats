// Test data written as plain rows, and encoded the way specstats/build.py
// lays out data.json.

import type { RawData } from "../src/lib/data.ts";

export interface Table {
  meta: RawData["meta"];
  event_types: string[];
  repos: RawData["repos"];
  /** Values, not differences. `is_pr` is all 1s (PRs) and `hours_to_close`
   * all nulls if left out. */
  items: {
    repo: number[];
    number: number[];
    is_pr?: number[];
    created: number[];
    hours_to_merge: (number | null)[];
    hours_to_close?: (number | null)[];
  };
  /** [day, item, event type], each item's in time order. */
  events: [number, number, string][];
}

export function encode(t: Table): RawData {
  const n = t.items.repo.length;
  const number: number[] = [];
  const created: number[] = [];
  const last = new Map<number, [number, number]>();
  for (let i = 0; i < n; i++) {
    const r = t.items.repo[i];
    const [ln, lc] = last.get(r) ?? [0, 0];
    number.push(t.items.number[i] - ln);
    created.push(t.items.created[i] - lc);
    last.set(r, [t.items.number[i], t.items.created[i]]);
  }
  const counts = new Array<number>(n).fill(0);
  const day: number[] = [];
  const event: number[] = [];
  for (let i = 0; i < n; i++) {
    let prev = Math.max(t.items.created[i], 0);
    for (const [d, item, type] of t.events) {
      if (item !== i) continue;
      counts[i]++;
      day.push(d - prev);
      event.push(t.event_types.indexOf(type));
      prev = d;
    }
  }
  return {
    meta: t.meta,
    event_types: t.event_types,
    repos: t.repos,
    items: {
      ...t.items,
      number,
      is_pr: t.items.is_pr ?? new Array<number>(n).fill(1),
      created,
      hours_to_close: t.items.hours_to_close ?? new Array<null>(n).fill(null),
      events: counts,
    },
    events: { day, event },
  };
}

/** The same table with its items in another order, so a view that relies
 * on the order of items or events gives different results. */
export function shuffled(t: Table): Table {
  const n = t.items.repo.length;
  // A fixed shuffle: Fisher–Yates with a small LCG.
  const order = Array.from({ length: n }, (_, i) => i);
  let seed = 12345;
  for (let i = n - 1; i > 0; i--) {
    seed = (seed * 1103515245 + 12345) % 2 ** 31;
    const j = seed % (i + 1);
    [order[i], order[j]] = [order[j], order[i]];
  }
  if (n > 1 && order.every((o, i) => o === i)) order.reverse();
  const to = new Array<number>(n);
  order.forEach((o, i) => (to[o] = i));
  const pick = <T>(xs: T[]) => order.map((o) => xs[o]);
  return {
    ...t,
    items: {
      repo: pick(t.items.repo),
      number: pick(t.items.number),
      is_pr: t.items.is_pr && pick(t.items.is_pr),
      created: pick(t.items.created),
      hours_to_merge: pick(t.items.hours_to_merge),
      hours_to_close: t.items.hours_to_close && pick(t.items.hours_to_close),
    },
    events: t.events.map(([d, i, e]) => [d, to[i], e]),
  };
}
