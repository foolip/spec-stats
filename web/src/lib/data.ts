// The data file `python3 -m specstats build` writes (docs/site-design.md):
// each table stored by column, indexes into lookup lists and tables, laid
// out to compress well (specstats/build.py).

export interface RawData {
  meta: { from: string; to: string };
  event_types: string[];
  repos: { name: string[]; standard: string[] };
  items: {
    repo: number[];
    /** Difference from the previous item of the same repo (the first of a repo's: its number). */
    number: number[];
    /** 1 for a PR, 0 for an issue. */
    is_pr: number[];
    /** Day of the item's created_at, from meta.from (negative before the window),
     * as a difference from the previous item of the same repo, like `number`. */
    created: number[];
    /** Hours from ready for review to merge, for PRs merged in the window:
     * whole hours, rounded up. */
    hours_to_merge: (number | null)[];
    /** Hours from creation to the last `closed` event, for issues closed at
     * the end of the window whose last close is in it: whole hours, rounded
     * up. */
    hours_to_close: (number | null)[];
    /** How many of `events` are this item's, which follow the previous item's. */
    events: number[];
  };
  /** Grouped by item, each item's in time order. `day` is the days since
   * the item's previous event, or for its first, since max(created, 0). */
  events: { day: number[]; event: number[] };
}

/** The data as the app uses it: the columns as typed arrays, with values
 * rather than differences, and each event's item.
 *
 * Events are grouped by item, each item's in time order. Nothing else
 * about the order of events or items is promised: code that needs events
 * in day order must sort them itself (test/helpers.ts runs views on
 * shuffled items to check). */
export interface Data {
  from: string;
  to: string;
  /** Number of days in the window, `from` to `to` inclusive. */
  days: number;
  eventTypes: string[];
  repos: { name: string[]; standard: string[] };
  items: {
    repo: Int32Array;
    number: Int32Array;
    /** 1 for a PR, 0 for an issue. */
    isPr: Uint8Array;
    created: Int32Array;
    hoursToMerge: Float64Array;
    hoursToClose: Float64Array;
  };
  events: { day: Int32Array; item: Int32Array; event: Int32Array };
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
  const lastNumber = new Int32Array(raw.repos.name.length);
  const lastCreated = new Int32Array(raw.repos.name.length);
  for (let i = 0; i < n; i++) {
    const r = repo[i];
    number[i] = lastNumber[r] += raw.items.number[i];
    created[i] = lastCreated[r] += raw.items.created[i];
  }
  const m = raw.events.day.length;
  const counted = raw.items.events.reduce((a, b) => a + b, 0);
  if (counted !== m) throw new Error(`items.events adds up to ${counted}, but there are ${m} events`);
  const day = new Int32Array(m);
  const item = new Int32Array(m);
  for (let i = 0, k = 0; i < n; i++) {
    let d = Math.max(created[i], 0);
    for (const end = k + raw.items.events[i]; k < end; k++) {
      day[k] = d += raw.events.day[k];
      item[k] = i;
    }
  }
  return {
    from: raw.meta.from,
    to: raw.meta.to,
    days: dayOf(raw.meta.from, raw.meta.to) + 1,
    eventTypes: raw.event_types,
    repos: raw.repos,
    items: {
      repo,
      number,
      isPr: Uint8Array.from(raw.items.is_pr),
      created,
      // NaN for PRs not merged in the window, and for issues.
      hoursToMerge: Float64Array.from(raw.items.hours_to_merge, (h) => h ?? NaN),
      // NaN for issues not closed in the window, and for PRs.
      hoursToClose: Float64Array.from(raw.items.hours_to_close, (h) => h ?? NaN),
    },
    events: { day, item, event: Int32Array.from(raw.events.event) },
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
