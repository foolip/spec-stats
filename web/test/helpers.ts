// Test data written as plain rows, and encoded the way specstats/build.py
// lays out data.json.

import type { RawData } from "../src/lib/data.ts";

export interface Table {
  meta: RawData["meta"];
  repos: RawData["repos"];
  /** Values, not differences. `kind` is all 1s (PRs not merged) and
   * `later_in_day` all 0s if left out. `closed` is the day of the last
   * close, from meta.from, or null while open. */
  items: {
    repo: number[];
    number: number[];
    kind?: number[];
    created: number[];
    closed: (number | null)[];
    later_in_day?: number[];
  };
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
  return {
    meta: t.meta,
    repos: t.repos,
    items: {
      repo: t.items.repo,
      number,
      kind: t.items.kind ?? new Array<number>(n).fill(1),
      created,
      closed: t.items.closed.map((c, i) => (c === null ? null : c - t.items.created[i])),
      later_in_day: t.items.later_in_day ?? new Array<number>(n).fill(0),
    },
  };
}

/** The same table with its items in another order, so a view that relies
 * on the order of items gives different results. */
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
  const pick = <T>(xs: T[]) => order.map((o) => xs[o]);
  return {
    ...t,
    items: {
      repo: pick(t.items.repo),
      number: pick(t.items.number),
      kind: t.items.kind && pick(t.items.kind),
      created: pick(t.items.created),
      closed: pick(t.items.closed),
      later_in_day: t.items.later_in_day && pick(t.items.later_in_day),
    },
  };
}
