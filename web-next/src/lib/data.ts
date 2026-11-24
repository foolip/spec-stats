// The published data file (`python3 -m specstats build`, `build/data.json`)
// and its decoded, in-memory form. See docs/site-design.md, "First version".

import { Calendar } from "./dates.ts";

export interface RawData {
  meta: { from: string; to: string };
  repos: { name: string[]; standard: string[] };
  items: {
    repo: number[];
    /** Difference from the previous item of the same repo. */
    number: number[];
    /** 0 issue, 1 PR not merged in the window, 2 PR merged in the window. */
    kind: number[];
    /** Day of creation from meta.from; difference from the previous item of the same repo. */
    created: number[];
    /** Days from creation to the last close, or null while open. */
    closed: (number | null)[];
    later_in_day: number[];
  };
}

export const ISSUE = 0;
export const PR_UNMERGED = 1;
export const PR_MERGED = 2;

export interface Repo {
  name: string;
  standard: string;
}

export interface Items {
  length: number;
  repo: Uint16Array;
  number: Uint32Array;
  kind: Uint8Array;
  /** Day of creation; negative before the window. */
  created: Int32Array;
  /** Day of the last close; Infinity while open. */
  closedDay: Float64Array;
  /** Time open in whole days, rounded up; NaN while open. */
  openDays: Float64Array;
}

export interface Data {
  from: string;
  to: string;
  /** Day index of the window's last day. */
  end: number;
  repos: Repo[];
  items: Items;
}

export function fromRaw(raw: RawData): Data {
  const end = new Calendar(raw.meta.from).day(raw.meta.to);
  const n = raw.items.repo.length;
  const items: Items = {
    length: n,
    repo: new Uint16Array(n),
    number: new Uint32Array(n),
    kind: new Uint8Array(n),
    created: new Int32Array(n),
    closedDay: new Float64Array(n),
    openDays: new Float64Array(n),
  };
  const lastNumber = new Map<number, number>();
  const lastCreated = new Map<number, number>();
  for (let i = 0; i < n; i++) {
    const repo = raw.items.repo[i];
    const seen = lastNumber.has(repo);
    const number = (seen ? lastNumber.get(repo)! : 0) + raw.items.number[i];
    const created = (seen ? lastCreated.get(repo)! : 0) + raw.items.created[i];
    lastNumber.set(repo, number);
    lastCreated.set(repo, created);
    const closed = raw.items.closed[i];
    items.repo[i] = repo;
    items.number[i] = number;
    items.kind[i] = raw.items.kind[i];
    items.created[i] = created;
    items.closedDay[i] = closed === null ? Infinity : created + closed;
    items.openDays[i] = closed === null ? NaN : closed + raw.items.later_in_day[i];
  }
  const repos = raw.repos.name.map((name, i) => ({ name, standard: raw.repos.standard[i] }));
  return { from: raw.meta.from, to: raw.meta.to, end, repos, items };
}
