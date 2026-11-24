import type { View } from "./state.ts";

export interface ViewTexts {
  tab: string;
  question: string;
  noun: string;
  openHeading: string;
  openedHeading: string;
  closedHeading: string;
  closedTile: string;
  closedColumn: string;
}

export const TEXTS: Record<View, ViewTexts> = {
  issues: {
    tab: "Issues",
    question: "How many issues are open, how old are they, and how quickly are they closed?",
    noun: "issues",
    openHeading: "Open issues, by year opened",
    openedHeading: "Issues opened, by time to close",
    closedHeading: "Issues closed, by time open",
    closedTile: "Closed",
    closedColumn: "Closed",
  },
  reviews: {
    tab: "Reviews",
    question: "How many PRs are waiting, how old are they, and how quickly are they merged?",
    noun: "PRs",
    openHeading: "Open PRs, by year opened",
    openedHeading: "PRs opened, by time to close",
    closedHeading: "PRs merged or closed, by time open",
    closedTile: "Merged",
    closedColumn: "Merged",
  },
};

export const SITE_NAME = "Living Statistics";

export function pageTitle(view: View, standard: string | null): string {
  return `${TEXTS[view].tab} · ${standard ?? "WHATWG"} ${SITE_NAME}`;
}
