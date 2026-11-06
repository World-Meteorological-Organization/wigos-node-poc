import { computed, ref, toValue, watch } from "vue";
import { checkWigosIdentifiers } from "../api";
import { wigosIdsToCheck } from "../wmdr";

const DEBOUNCE_MS = 400;

// Looks up whether WIGOS IDs are already registered to a station. `ids` and
// `ownIds` are refs or getters. Returns a function giving each ID's status:
// null (not checked: malformed, empty or one of `ownIds`), "checking",
// "available", "taken" or "error". Called from a template or computed, it
// tracks the results, so the caller updates when a check comes back.
//
// Results are cached per ID, so a reply that arrives after the user has moved
// on is still correct for the ID it was about. Failed lookups are retried the
// next time the set of IDs to check changes.
export function useWigosIdAvailability(ids, ownIds) {
  const results = ref({});
  const checkable = computed(() => wigosIdsToCheck(toValue(ids), toValue(ownIds)));
  const pendingKey = computed(() =>
    checkable.value.filter((id) => results.value[id] === undefined || results.value[id] === "error").join(" ")
  );

  watch(
    pendingKey,
    (key, _previous, onCleanup) => {
      if (!key) return;
      const batch = key.split(" ");
      const timer = setTimeout(() => {
        checkWigosIdentifiers(batch)
          .then((taken) => batch.map((id) => [id, taken[id] ? "taken" : "available"]))
          .catch(() => batch.map((id) => [id, "error"]))
          .then((entries) => {
            results.value = { ...results.value, ...Object.fromEntries(entries) };
          });
      }, DEBOUNCE_MS);
      onCleanup(() => clearTimeout(timer));
    },
    { immediate: true }
  );

  return (id) => (checkable.value.includes(id) ? results.value[id] ?? "checking" : null);
}
