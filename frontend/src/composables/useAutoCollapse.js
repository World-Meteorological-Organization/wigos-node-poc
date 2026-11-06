import { onBeforeUnmount, onMounted, toValue } from "vue";

// Calls `collapse(keys)` with the keys of the cards that focus has just left.
// `cards` (ref or getter) maps a key to its card element. Listens globally
// rather than for blur within each card, so a card that was never focused in
// the first place (e.g. one expanded by default) still collapses when focus
// moves elsewhere on the page. `enabled` (ref or getter) switches it off.
export function useAutoCollapse(cards, collapse, enabled = true) {
  // The cards that `target` is outside of - decided at focus time, so a card
  // added by the click that moved focus isn't included.
  const keysOutside = (target) => {
    // Dialogs and dropdown menus are teleported out of the card's DOM subtree,
    // but they still edit that card's data, so they don't count as leaving.
    if (target?.closest?.(".v-overlay-container")) return [];
    return Object.entries(toValue(cards))
      .filter(([, node]) => node && !node.contains(target))
      .map(([key]) => key);
  };
  const collapseKeys = (keys) => {
    if (keys.length) collapse(keys);
  };

  // Focus moves on pointerdown, before the click. Collapsing a card then
  // shifts the layout, so the pointerup lands on a different element and the
  // click (e.g. on a "+ Add" button below the card) is lost. Wait until the
  // pointer is released and the click has been dispatched.
  let pointerDown = false;
  let pendingKeys = null;
  const handlePointerDown = () => {
    pointerDown = true;
  };
  const handlePointerUp = () => {
    pointerDown = false;
    if (!pendingKeys) return;
    const keys = pendingKeys;
    pendingKeys = null;
    setTimeout(() => collapseKeys(keys), 0);
  };
  const handleFocusIn = (e) => {
    if (!toValue(enabled)) return;
    if (pointerDown) pendingKeys = keysOutside(e.target);
    else collapseKeys(keysOutside(e.target));
  };

  onMounted(() => {
    document.addEventListener("pointerdown", handlePointerDown, true);
    document.addEventListener("pointerup", handlePointerUp, true);
    document.addEventListener("pointercancel", handlePointerUp, true);
    document.addEventListener("focusin", handleFocusIn);
  });
  onBeforeUnmount(() => {
    document.removeEventListener("pointerdown", handlePointerDown, true);
    document.removeEventListener("pointerup", handlePointerUp, true);
    document.removeEventListener("pointercancel", handlePointerUp, true);
    document.removeEventListener("focusin", handleFocusIn);
  });
}
