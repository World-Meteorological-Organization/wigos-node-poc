// Session-cookie auth against the Django backend. In dev the Vite proxy keeps
// everything on one origin, so the sessionid / csrftoken cookies are first-party.

const API_URL = import.meta.env.VITE_API_URL || "";

function getCookie(name) {
  const match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[1]) : null;
}

// Header to attach to unsafe (POST/PUT) requests so SessionAuthentication's CSRF
// check passes. Empty object when there's no cookie yet.
export function csrfHeader() {
  const token = getCookie("csrftoken");
  return token ? { "X-CSRFToken": token } : {};
}

// Ensure the csrftoken cookie exists.
export async function initCsrf() {
  await fetch(`${API_URL}/api/csrf/`, { credentials: "include" });
}

export async function login(username, password) {
  const res = await fetch(`${API_URL}/api/login/`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `Login failed: ${res.status}`);
  }
  await initCsrf(); // Django's login() rotates the CSRF token; refresh ours
  return data;
}

export async function logout() {
  await fetch(`${API_URL}/api/logout/`, {
    method: "POST",
    credentials: "include",
    headers: { ...csrfHeader() },
  }).catch(() => {});
}

// Resolves to the user object, or null when not authenticated.
export async function fetchCurrentUser() {
  const res = await fetch(`${API_URL}/api/whoami/`, { credentials: "include" });
  return res.ok ? res.json() : null;
}
