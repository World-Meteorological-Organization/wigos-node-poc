import { onScopeDispose, ref, shallowRef } from "vue";
import { CODELISTS, loadCodelist } from "../codelists";

// Loads the named codelists once. Each name maps to [] until it has loaded
// (or when it fails to load); `loaded` turns true once all of them are in.
export function useCodelists(names = Object.keys(CODELISTS)) {
  const loaded = ref(false);
  const codelists = shallowRef(Object.fromEntries(names.map((name) => [name, []])));

  let cancelled = false;
  onScopeDispose(() => {
    cancelled = true;
  });
  Promise.all(names.map((name) => loadCodelist(CODELISTS[name]))).then((lists) => {
    if (cancelled) return;
    codelists.value = Object.fromEntries(names.map((name, i) => [name, lists[i]]));
    loaded.value = true;
  });

  return { loaded, codelists };
}
