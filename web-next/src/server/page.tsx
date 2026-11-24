// Renders a view's page at build time, with the default state's figures.

import { preload } from "react-dom";
import Dashboard from "@/components/Dashboard.tsx";
import { pageTitle } from "@/lib/texts.ts";
import Footer from "@/components/Footer.tsx";
import { computeModel } from "@/lib/model.ts";
import { defaultState, VIEWS, type View } from "@/lib/state.ts";
import { dataUrl, loadData } from "./data.ts";

export function viewParams() {
  return VIEWS.map((view) => ({ view }));
}

export function specParams() {
  const { data } = loadData();
  return VIEWS.flatMap((view) => data.repos.map((r) => ({ view, spec: r.name })));
}

export function title(view: View, spec: string | null) {
  const { data } = loadData();
  return pageTitle(view, spec ? (data.repos.find((r) => r.name === spec)?.standard ?? null) : null);
}

export default function ViewPage({ view, spec }: { view: View; spec: string | null }) {
  const { data } = loadData();
  const win = { from: data.from, to: data.to };
  const initial = defaultState(win, view, spec);
  const url = dataUrl();
  preload(url, { as: "fetch", crossOrigin: "anonymous" });
  return (
    <>
      <Dashboard win={win} repos={data.repos} initial={initial} model={computeModel(data, initial)} dataUrl={url} />
      <Footer win={win} />
    </>
  );
}
