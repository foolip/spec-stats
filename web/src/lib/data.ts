// The data file `python3 -m specstats build` writes (docs/site-design.md):
// each table stored by column, indexes into lookup lists and tables, laid
// out to compress well (specstats/build.py).

export interface RawData {
  meta: { from: string; to: string };
  repos: { name: string[]; standard: string[] };
  items: {
    repo: number[];
    /** Difference from the previous item of the same repo (the first of a repo's: its number). */
    number: number[];
    /** 0 for an issue, 1 for a PR not merged in the window, 2 for a PR merged in it. */
    kind: number[];
    /** Day of the item's created_at, from meta.from (negative before the window),
     * as a difference from the previous item of the same repo, like `number`. */
    created: number[];
    /** For an item closed at the end of the window, the day of its last
     * close (a PR's merge), as days after `created`; null while open. */
    closed: (number | null)[];
    /** 1 if the last close was at a later time of day than the creation:
     * the time open, in whole days rounded up, is `closed + later_in_day`. */
    later_in_day: number[];
  };
}

/** The data as the app uses it: the columns as typed arrays, with values
 * rather than differences. Nothing about the order of items is promised
 * (test/helpers.ts runs views on shuffled items to check).
 *
 * An item is open from its creation (or the window's start) to its last
 * close, as GitHub search sees it: closes followed by a reopen are left
 * out of the data. */
export interface Data {
  from: string;
  to: string;
  /** Number of days in the window, `from` to `to` inclusive. */
  days: number;
  repos: { name: string[]; standard: string[] };
  items: {
    repo: Int32Array;
    number: Int32Array;
    /** 1 for a PR, 0 for an issue. */
    isPr: Uint8Array;
    /** 1 for a PR merged in the window (at its last close), else 0. */
    merged: Uint8Array;
    created: Int32Array;
    /** Day of the last close, from `from`; Infinity for items open at
     * the end of the window. */
    closed: Float64Array;
    /** Time from creation to the last close in whole days, rounded up:
     * within that many days. NaN for items open at the end. */
    daysOpen: Float64Array;
  };
}

const DAY_MS = 86_400_000;

export function parseDate(date: string): number {
  return Date.parse(`${date}T00:00:00Z`);
}

export function formatDate(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

/** Days from `from` to `date`, both YYYY-MM-DD. */
export function dayOf(from: string, date: string): number {
  return Math.round((parseDate(date) - parseDate(from)) / DAY_MS);
}

/** The YYYY-MM-DD date of day `day` after `from`. */
export function dateOf(from: string, day: number): string {
  return formatDate(parseDate(from) + day * DAY_MS);
}

export function fromRaw(raw: RawData): Data {
  const n = raw.items.repo.length;
  const repo = Int32Array.from(raw.items.repo);
  const number = new Int32Array(n);
  const created = new Int32Array(n);
  const closed = new Float64Array(n).fill(Infinity);
  const daysOpen = new Float64Array(n).fill(NaN);
  const lastNumber = new Int32Array(raw.repos.name.length);
  const lastCreated = new Int32Array(raw.repos.name.length);
  for (let i = 0; i < n; i++) {
    const r = repo[i];
    number[i] = lastNumber[r] += raw.items.number[i];
    created[i] = lastCreated[r] += raw.items.created[i];
    const c = raw.items.closed[i];
    if (c !== null) {
      closed[i] = created[i] + c;
      daysOpen[i] = c + raw.items.later_in_day[i];
    }
  }
  return {
    from: raw.meta.from,
    to: raw.meta.to,
    days: dayOf(raw.meta.from, raw.meta.to) + 1,
    repos: raw.repos,
    items: {
      repo,
      number,
      isPr: Uint8Array.from(raw.items.kind, (k) => (k > 0 ? 1 : 0)),
      merged: Uint8Array.from(raw.items.kind, (k) => (k === 2 ? 1 : 0)),
      created,
      closed,
      daysOpen,
    },
  };
}

let loading: Promise<Data> | undefined;

/** The data file, fetched once. */
export function load(url = "data.json"): Promise<Data> {
  loading ??= fetch(url).then(async (resp) => {
    if (!resp.ok) throw new Error(`${url}: HTTP ${resp.status}`);
    return fromRaw((await resp.json()) as RawData);
  });
  return loading;
}
