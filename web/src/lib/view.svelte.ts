import type { Controller } from "../controller.ts";
import type { State } from "./url.ts";

/** The controller's state, as Svelte state: updated on every change. */
export function viewState(controller: Controller): State {
  const view = $state({ ...controller.state });
  controller.subscribe((s) => Object.assign(view, s));
  return view;
}
