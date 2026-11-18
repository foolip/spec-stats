import type { Repos } from "./url.ts";

/** The shorter way to write a set of repos: all, only some, or all but some. */
export function reposFor(selected: Set<string>, names: string[]): Repos {
  const missing = names.filter((n) => !selected.has(n)).sort();
  if (missing.length === 0 || selected.size === 0) return { mode: "all" };
  const only = names.filter((n) => selected.has(n)).sort();
  return missing.length < only.length ? { mode: "except", names: missing } : { mode: "only", names: only };
}
