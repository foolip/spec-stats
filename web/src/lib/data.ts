// The data file `python3 -m specstats build` writes (docs/site-design.md):
// each table stored by column, indexes into lookup lists and tables.

export interface RawData {
  meta: { from: string; to: string };
  event_types: string[];
  repos: { name: string[]; standard: string[] };
  items: {
    repo: number[];
    number: number[];
    /** Day of the PR's created_at, from meta.from; negative before the window. */
    created: number[];
    /** Hours from ready for review to merge, for PRs merged in the window. */
    hours_to_merge: (number | null)[];
  };
  events: { day: number[]; item: number[]; event: number[] };
}

/** The data as the app uses it: the same columns, as typed arrays. */
export interface Data {
  from: string;
  to: string;
  /** Number of days in the window, `from` to `to` inclusive. */
  days: number;
  eventTypes: string[];
  repos: { name: string[]; standard: string[] };
  items: { repo: Int32Array; number: Int32Array; created: Int32Array; hoursToMerge: Float64Array };
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
  return {
    from: raw.meta.from,
    to: raw.meta.to,
    days: dayOf(raw.meta.from, raw.meta.to) + 1,
    eventTypes: raw.event_types,
    repos: raw.repos,
    items: {
      repo: Int32Array.from(raw.items.repo),
      number: Int32Array.from(raw.items.number),
      created: Int32Array.from(raw.items.created),
      // NaN for PRs not merged in the window.
      hoursToMerge: Float64Array.from(raw.items.hours_to_merge, (h) => h ?? NaN),
    },
    events: {
      day: Int32Array.from(raw.events.day),
      item: Int32Array.from(raw.events.item),
      event: Int32Array.from(raw.events.event),
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
