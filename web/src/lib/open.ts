// Open PRs or issues over time: each item's open and draft state replayed
// from its events, counted at the end of every day. Issues are never
// drafts, so all of them count as ready.

import { dateOf, type Data } from "./data.ts";

export interface OpenSeries {
  /** Open items ready for review (every open issue) at the end of each day
   * of the window. */
  ready: Int32Array;
  /** Open draft PRs at the end of each day. */
  draft: Int32Array;
}

/** Which items are of a kind: PRs or issues. */
export type Kind = "pr" | "issue";

const OPENS = new Set(["_carried_in", "_created", "reopened"]);
const CLOSES = new Set(["closed"]);
const DRAFTS = new Set(["_carried_in_as_draft", "_created_as_draft", "convert_to_draft"]);
const READIES = new Set(["ready_for_review"]);

/** Each item's group: 0 for the items of a kind, -1 for the rest. */
export function ofKind(data: Data, kind: Kind): Int32Array {
  const pr = kind === "pr" ? 1 : 0;
  return Int32Array.from(data.items.isPr, (p) => (p === pr ? 0 : -1));
}

/** For each repo index: its open items of a kind, ready and draft, every day. */
export function openByRepo(data: Data, kind: Kind): OpenSeries[] {
  return openByGroup(data, ofKind(data, kind), 1).map((groups) => groups[0]);
}

/** For each repo index and each group (`group[item]`, 0 to groups − 1;
 * items in group -1 are left out): its open items, ready and draft, every
 * day. */
export function openByGroup(data: Data, group: Int32Array, groups: number): OpenSeries[][] {
  const kinds = data.eventTypes.map((t) =>
    OPENS.has(t) ? 1 : CLOSES.has(t) ? 2 : DRAFTS.has(t) ? 3 : READIES.has(t) ? 4 : 0,
  );
  const repoCount = data.repos.name.length;
  // Changes per day, then a running sum: deltas[repo][group][day].
  const blank = () => Array.from({ length: groups }, () => new Int32Array(data.days + 1));
  const dReady = Array.from({ length: repoCount }, blank);
  const dDraft = Array.from({ length: repoCount }, blank);
  const isOpen = new Uint8Array(data.items.repo.length);
  const isDraft = new Uint8Array(data.items.repo.length);
  const { day, item, event } = data.events;
  for (let k = 0; k < day.length; k++) {
    const i = item[k];
    if (group[i] < 0) continue;
    const before = isOpen[i] ? (isDraft[i] ? 2 : 1) : 0;
    switch (kinds[event[k]]) {
      case 1: isOpen[i] = 1; break;
      case 2: isOpen[i] = 0; break;
      case 3: isDraft[i] = 1; break;
      case 4: isDraft[i] = 0; break;
      default: continue;
    }
    const after = isOpen[i] ? (isDraft[i] ? 2 : 1) : 0;
    if (before === after) continue;
    const r = data.items.repo[i];
    const g = group[i];
    if (before === 1) dReady[r][g][day[k]]--;
    if (before === 2) dDraft[r][g][day[k]]--;
    if (after === 1) dReady[r][g][day[k]]++;
    if (after === 2) dDraft[r][g][day[k]]++;
  }
  return dReady.map((gs, r) =>
    gs.map((dr, g) => ({ ready: runningSum(dr, data.days), draft: runningSum(dDraft[r][g], data.days) })),
  );
}

function runningSum(deltas: Int32Array, days: number): Int32Array {
  const out = new Int32Array(days);
  let n = 0;
  for (let d = 0; d < days; d++) out[d] = n += deltas[d];
  return out;
}

/** The sum of the chosen repos' series. */
export function total(series: OpenSeries[], repos: Iterable<number>, days: number): OpenSeries {
  const ready = new Int32Array(days);
  const draft = new Int32Array(days);
  for (const r of repos) {
    for (let d = 0; d < days; d++) {
      ready[d] += series[r].ready[d];
      draft[d] += series[r].draft[d];
    }
  }
  return { ready, draft };
}

export interface Cohorts {
  /** Labels, oldest first: "older", "2022", …, "2026". */
  labels: string[];
  /** Each item's cohort: an index into labels. */
  of: Int32Array;
}

/** Items grouped by the year they were opened: one group for each of the
 * last `years` calendar years up to the window's end, and one for every item
 * opened before those. A group only shrinks once its year is over. */
export function yearCohorts(data: Data, years = 5): Cohorts {
  const last = Number(data.to.slice(0, 4));
  const first = last - years + 1;
  const labels = ["older"];
  for (let y = first; y <= last; y++) labels.push(String(y));
  const of = new Int32Array(data.items.created.length);
  for (let i = 0; i < of.length; i++) {
    const y = Number(dateOf(data.from, data.items.created[i]).slice(0, 4));
    of[i] = y < first ? 0 : y - first + 1;
  }
  return { labels, of };
}
