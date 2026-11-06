import { onBeforeUnmount, onMounted, ref } from "vue";
import { fetchCurrentUser, initCsrf, logout as apiLogout } from "../auth";

// Session state: status is "loading", "authenticated" or "anonymous". Any API
// call that gets a 401 dispatches "auth:unauthenticated" (see api.js), which
// drops back to the login page.
export function useAuth() {
  const status = ref("loading");
  const user = ref(null);

  const setUser = (next) => {
    user.value = next;
    status.value = next ? "authenticated" : "anonymous";
  };
  const onUnauthenticated = () => setUser(null);

  onMounted(() => {
    initCsrf()
      .then(fetchCurrentUser)
      .then(setUser)
      .catch(() => setUser(null));
    window.addEventListener("auth:unauthenticated", onUnauthenticated);
  });
  onBeforeUnmount(() => window.removeEventListener("auth:unauthenticated", onUnauthenticated));

  async function logout() {
    await apiLogout();
    setUser(null);
  }

  return { status, user, setUser, logout };
}
