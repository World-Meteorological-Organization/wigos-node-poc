import { KEY_COLUMNS, applyRowsWith, makeRow, setOrDelete, stationKeys } from "./common";

// WIGOS identifiers: one row per station. The current primary ID is shown
// read-only; a new primary is entered beside it (empty keeps the current one).
// Up to three additional IDs are edited in place. A station that already has
// more than three keeps the rest untouched (`extraAdditionalIds`).

export const MAX_ADDITIONAL_IDS = 3;

const ADDITIONAL_KEYS = Array.from({ length: MAX_ADDITIONAL_IDS }, (_, i) => `additional_id_${i + 1}`);

export const columns = [
  { ...KEY_COLUMNS.wigosId, key: "old_wigos_id", label: "Current WIGOS ID" },
  KEY_COLUMNS.stationName,
  { key: "new_wigos_id", label: "New WIGOS ID (empty: keep)", kind: "wsi", width: 200 },
  ...ADDITIONAL_KEYS.map((key, i) => ({ key, label: `Additional ID ${i + 1}`, kind: "wsi", width: 190 })),
];

// A file row is matched to a grid row on the current ID.
export const importKeys = ["old_wigos_id"];

export function toRows(entries) {
  return entries.map((entry) => {
    const { station_name, wigos_id } = stationKeys(entry);
    const additional = entry.record.properties?.additionalIds || [];
    const slots = Object.fromEntries(ADDITIONAL_KEYS.map((key, i) => [key, additional[i] || ""]));
    return makeRow(
      String(entry.stationId),
      entry.stationId,
      { old_wigos_id: wigos_id, station_name },
      { new_wigos_id: "", ...slots },
      { extraAdditionalIds: additional.slice(MAX_ADDITIONAL_IDS) }
    );
  });
}

const additionalIn = (cells) => ADDITIONAL_KEYS.map((key) => cells[key]).filter(Boolean);

export function applyRows(entries, rows) {
  return applyRowsWith(entries, rows, columns, (record, row, changed) => {
    if (changed.has("new_wigos_id") && row.cells.new_wigos_id) record.id = row.cells.new_wigos_id;
    // An empty list removes the key (the schema wants at least one item).
    if (ADDITIONAL_KEYS.some((key) => changed.has(key))) {
      record.properties = record.properties || {};
      setOrDelete(record.properties, "additionalIds", [...additionalIn(row.cells), ...(row.extraAdditionalIds || [])]);
    }
  });
}

// Every ID the stations will have, for the duplicate and availability checks.
export const idsInRows = (rows) =>
  rows.flatMap((row) => [row.cells.new_wigos_id || row.cells.old_wigos_id, ...additionalIn(row.cells), ...(row.extraAdditionalIds || [])]);

// The IDs the selected stations own now; they don't need an availability check.
export const ownIdsInRows = (rows) =>
  rows.flatMap((row) => [row.original.old_wigos_id, ...additionalIn(row.original), ...(row.extraAdditionalIds || [])]);

// Shown on a station's row when it has IDs beyond the editable slots.
export const rowNote = (row) =>
  row.extraAdditionalIds?.length
    ? `Also has ${row.extraAdditionalIds.join(", ")} (kept as is; only ${MAX_ADDITIONAL_IDS} additional IDs are editable here)`
    : null;
