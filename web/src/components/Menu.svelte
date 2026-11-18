<script lang="ts">
  // A button that opens a panel: the native Popover API, so the panel is in
  // the top layer (never clipped or see-through because of the controls bar)
  // and closes on Escape or a click outside. On wide screens it's placed
  // under its button with CSS anchor positioning (popovertarget makes the
  // button its implicit anchor), or by place() where that isn't supported
  // (Firefox, in November 2026); on narrow screens it's a bottom sheet.
  import type { Snippet } from "svelte";

  interface Props {
    /** The panel's accessible name. */
    label: string;
    /** The button's content. */
    button: Snippet;
    children: Snippet;
    buttonClass?: string;
    /** Marks the button as showing a chosen value (styling only). */
    active?: boolean;
  }
  let { label, button: buttonContent, children, buttonClass = "menu-button", active = false }: Props = $props();

  const id = `menu-${Math.random().toString(36).slice(2)}`;
  let button: HTMLButtonElement;
  let panel: HTMLDivElement;
  let open = $state(false);

  const anchored = typeof CSS !== "undefined" && CSS.supports("position-area: block-end");
  const narrow = () => matchMedia("(max-width: 640px)").matches;

  function place() {
    if (anchored || narrow()) {
      panel.style.removeProperty("left");
      panel.style.removeProperty("top");
      return;
    }
    const r = button.getBoundingClientRect();
    const left = Math.max(8, Math.min(r.left, innerWidth - panel.offsetWidth - 8));
    panel.style.left = `${left}px`;
    panel.style.top = `${r.bottom + 6}px`;
  }

  function onToggle(e: ToggleEvent) {
    open = e.newState === "open";
    if (open) place();
  }

  $effect(() => {
    if (!open || anchored) return;
    addEventListener("resize", place);
    addEventListener("scroll", place, true);
    return () => {
      removeEventListener("resize", place);
      removeEventListener("scroll", place, true);
    };
  });
</script>

<button
  bind:this={button}
  type="button"
  class={buttonClass}
  popovertarget={id}
  aria-expanded={open}
  data-active={active || undefined}
>
  {@render buttonContent()}
</button>
<div bind:this={panel} {id} popover="auto" class="menu" role="dialog" aria-label={label} ontoggle={onToggle}>
  {@render children()}
  <button type="button" class="menu-done" popovertarget={id} popovertargetaction="hide">Done</button>
</div>
