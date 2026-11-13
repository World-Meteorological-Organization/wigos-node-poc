import { parseCsv } from "./csv";
import { csrfHeader } from "./auth";

const API_URL = import.meta.env.VITE_API_URL || "";

// Notify the app when the session is gone so it can drop back to the login page.
function handle401(res) {
  if (res.status === 401) {
    window.dispatchEvent(new Event("auth:unauthenticated"));
  }
  return res;
}

export async function getHello() {
  const res = handle401(await fetch(`${API_URL}/api/hello/`, { credentials: "include" }));
  if (!res.ok) {
    throw new Error(`API request failed: ${res.status}`);
  }
  return res.json();
}

export async function saveStation(stationId, record) {
  const url = stationId == null ? `${API_URL}/api/wmdrv2/` : `${API_URL}/api/wmdrv2/${encodeURIComponent(stationId)}`;
  const res = handle401(await fetch(url, {
    method: stationId == null ? "POST" : "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json", ...csrfHeader() },
    body: JSON.stringify(record),
  }));
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || `API request failed: ${res.status}`);
  }
  return data;
}

export async function getStation(stationId) {
  const res = handle401(await fetch(`${API_URL}/api/wmdrv2/${encodeURIComponent(stationId)}`, {
    credentials: "include",
  }));
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || `API request failed: ${res.status}`);
  }
  return data;
}

// Returns { [stationId]: record } for the given stations; unknown IDs are left out.
export async function getStations(stationIds) {
  const params = new URLSearchParams(stationIds.map((id) => ["station_id", id]));
  const res = handle401(await fetch(`${API_URL}/api/wmdrv2/batch/?${params}`, { credentials: "include" }));
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || `API request failed: ${res.status}`);
  }
  return data;
}

// updates: [{ station_id, wmdrv2 }]. Returns { dry_run, summary, results }
// with a result per update; one station failing doesn't stop the others.
export async function saveStationsBatch(updates, { dryRun = false } = {}) {
  const res = handle401(await fetch(`${API_URL}/api/wmdrv2/batch/`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", ...csrfHeader() },
    body: JSON.stringify({ dry_run: dryRun, updates }),
  }));
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || data.error || `API request failed: ${res.status}`);
  }
  return data;
}

export async function listMyStations() {
  const res = handle401(await fetch(`${API_URL}/api/my_stations/`, { credentials: "include" }));
  if (!res.ok) {
    throw new Error(`API request failed: ${res.status}`);
  }
  return res.json();
}

export async function listMyIssuers() {
  const res = handle401(await fetch(`${API_URL}/api/my_issuer_of_identifiers/`, {
    credentials: "include",
  }));
  if (!res.ok) {
    throw new Error(`API request failed: ${res.status}`);
  }
  return res.json();
}

// Returns { [wigosId]: boolean }, true when a station already uses the ID
// as its primary or one of its additional identifiers.
export async function checkWigosIdentifiers(ids) {
  const params = new URLSearchParams(ids.map((id) => ["wigos_identifier", id]));
  const res = handle401(await fetch(`${API_URL}/api/check_wigosidentifiers/?${params}`, {
    credentials: "include",
  }));
  if (!res.ok) {
    throw new Error(`API request failed: ${res.status}`);
  }
  return res.json();
}

// The publication state of the stations the user can edit, one row per station,
// latest version first. Returns { count, next, previous, results }. filters:
// { status, limit, offset }.
export async function listPublications(filters = {}) {
  const params = new URLSearchParams(Object.entries(filters).filter(([, value]) => value != null));
  const res = handle401(await fetch(`${API_URL}/api/publications/?${params}`, { credentials: "include" }));
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `API request failed: ${res.status}`);
  }
  return data;
}

// Publishes the station's current record again, whatever its status; returns its
// updated row. An error (e.g. a station the user can't edit) is thrown with the reason.
export async function retryPublication(stationId) {
  const res = handle401(await fetch(`${API_URL}/api/publications/${encodeURIComponent(stationId)}/retry/`, {
    method: "POST",
    credentials: "include",
    headers: csrfHeader(),
  }));
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `API request failed: ${res.status}`);
  }
  return data;
}

export async function getCodelist(scheme) {
  const res = await fetch(`${API_URL}/api/codelists/${scheme}.csv`, { credentials: "include" });
  if (!res.ok) {
    throw new Error(`Failed to load codelist ${scheme}: ${res.status}`);
  }
  const text = await res.text();
  return parseCsv(text)
    .map((row) => ({
      code: row["skos:notation"],
      label: row["rdfs:label"] || row["skos:notation"],
      id: (row["@id"] || "").replace(/^<|>$/g, ""),
      // Stored as a quoted RDF literal with a language tag, e.g. 'Africa'@en.
      description: (row["dct:description"] || "").replace(/@[A-Za-z-]+$/, "").replace(/^'([\s\S]*)'$/, "$1").trim(),
    }))
    .filter((entry) => entry.code);
}
