// Open PRs over time: each PR's open and draft state replayed from its
// events, counted at the end of every day.

import type { Data } from "./data.ts";

export interface OpenSeries {
  /** Open PRs ready for review at the end of each day of the window. */
  ready: Int32Array;
  /** Open draft PRs at the end of each day. */
  draft: Int32Array;
}

const OPENS = new Set(["_carried_in", "_created", "reopened"]);
const CLOSES = new Set(["closed"]);
const DRAFTS = new Set(["_carried_in_as_draft", "_created_as_draft", "convert_to_draft"]);
const READIES = new Set(["ready_for_review"]);

/** For each repo index: its open PRs, ready and draft, every day. */
export function openByRepo(data: Data): OpenSeries[] {
  const kinds = data.eventTypes.map((t) =>
    OPENS.has(t) ? 1 : CLOSES.has(t) ? 2 : DRAFTS.has(t) ? 3 : READIES.has(t) ? 4 : 0,
  );
  const repoCount = data.repos.name.length;
  // Changes per day, then a running sum: deltas[repo][day].
  const dReady = Array.from({ length: repoCount }, () => new Int32Array(data.days + 1));
  const dDraft = Array.from({ length: repoCount }, () => new Int32Array(data.days + 1));
  const isOpen = new Uint8Array(data.items.repo.length);
  const isDraft = new Uint8Array(data.items.repo.length);
  const { day, item, event } = data.events;
  for (let k = 0; k < day.length; k++) {
    const i = item[k];
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
    if (before === 1) dReady[r][day[k]]--;
    if (before === 2) dDraft[r][day[k]]--;
    if (after === 1) dReady[r][day[k]]++;
    if (after === 2) dDraft[r][day[k]]++;
  }
  return dReady.map((dr, r) => ({ ready: runningSum(dr, data.days), draft: runningSum(dDraft[r], data.days) }));
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
