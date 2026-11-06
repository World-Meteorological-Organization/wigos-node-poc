import { WIGOS_ID_PATTERN } from "../wmdr";
import { codelistOptions } from "../codelists";
import { toCsv } from "../csv";

// Shared pieces of the batch operations. A grid row is
//   { id, stationId, cells: { [column]: string }, original: { [column]: string }, ...position }
// Every cell is a string, so the grid, the clipboard and CSV/XLSX files all
// handle the same values. Codelist cells hold the concept's notation.

// ---------------------------------------------------------------------------
// Columns

// Kinds: key (read-only), text, number, numbers (";"-list of numbers), date
// (interval bound), codelist, wsi, wsis (";"-list of WIGOS IDs).
export const KEY_COLUMNS = {
  wigosId: { key: "wigos_id", label: "WIGOS ID", kind: "key", width: 170 },
  stationName: { key: "station_name", label: "Station", kind: "key", width: 180 },
  observedProperty: { key: "observed_property", label: "Observed property", kind: "key", width: 200 },
};

export const isEditable = (column) => column.kind !== "key";

// A column with `lockedOnExisting` identifies existing rows (e.g. the
// programme of an affiliation) and can only be set on rows being added. A
// key column with `choices(row)` can be set on added rows too, to one of
// those choices only (e.g. an observation the station already has).
export const isCellEditable = (column, row) =>
  column.kind === "key"
    ? !!(column.choices && row?.isNew)
    : !(column.lockedOnExisting && !row?.isNew);

// The choices of `column` a cell names, by label or alias (case-insensitive):
// [{ label, aliases, ... }].
export function findChoices(column, row, text) {
  const value = (text ?? "").trim().toLowerCase();
  if (!value || !column.choices) return [];
  return column.choices(row).filter((choice) =>
    [choice.label, ...(choice.aliases || [])].some((candidate) => String(candidate).toLowerCase() === value)
  );
}

// ---------------------------------------------------------------------------
// Lists

export const LIST_SEPARATOR = ";";

export const splitList = (text) =>
  (text ?? "")
    .split(LIST_SEPARATOR)
    .map((item) => item.trim())
    .filter(Boolean);

export const joinList = (items) => (items || []).map(String).join(LIST_SEPARATOR);

// ---------------------------------------------------------------------------
// Concepts and codelists

// Same codelist entry: on the concept URI when both have one (notations can
// collide across codelists), otherwise on the notation.
export function sameConcept(a, b) {
  if (!a || !b) return !a && !b;
  if (a.url && b.url) return a.url === b.url;
  return String(a.id ?? "") === String(b.id ?? "");
}

export const conceptCell = (concept) => (concept?.id != null ? String(concept.id) : "");

// The codelist entry a cell refers to, by notation, label or URI.
export function findCodelistOption(options, text) {
  const value = (text ?? "").trim();
  if (!value) return null;
  const lower = value.toLowerCase();
  return (
    options.find((opt) => opt.code === value) ||
    options.find((opt) => opt.label.toLowerCase() === lower) ||
    options.find((opt) => opt.id && opt.id === value) ||
    options.find((opt) => opt.code.toLowerCase() === lower) ||
    null
  );
}

function conceptFromOption(opt) {
  const concept = { id: opt.code, title: opt.label };
  if (opt.description) concept.description = opt.description;
  if (opt.id) concept.url = opt.id;
  return concept;
}

// The concept to store for a codelist cell. The previous concept is kept
// when the cell still names it, so its title/description/url aren't rewritten.
export function conceptForCell(text, options, previous) {
  const value = (text ?? "").trim();
  if (!value) return null;
  if (previous && conceptCell(previous) === value) return previous;
  const opt = findCodelistOption(options, value);
  return opt ? conceptFromOption(opt) : { id: value };
}

// Label shown in the grid for a codelist cell.
export function codelistLabel(options, text) {
  const opt = findCodelistOption(options, text);
  return opt ? opt.label : text;
}

// Normalizes a typed, pasted or imported value: codelist labels become
// notations, a choice's alias becomes its label (needs the `row`);
// everything is trimmed.
export function normalizeCell(column, text, codelists, row) {
  const value = (text ?? "").toString().trim();
  if (column.choices && row) return findChoices(column, row, value)[0]?.label ?? value;
  if (column.kind === "date" && value && !DATE_PATTERNS.some((p) => p.test(value))) {
    return spreadsheetDateToIso(value, row?.original?.[column.key]) ?? value;
  }
  if (column.kind === "codelist" && value) {
    const opt = findCodelistOption(codelistOptions(column.codelist, codelists), value);
    return opt ? opt.code : value;
  }
  if (column.kind === "numbers" || column.kind === "wsis") return joinList(splitList(value));
  return value;
}

// ---------------------------------------------------------------------------
// Cell validation (the schema check on the whole record runs again before saving)

// Formats allowed for an interval bound / affiliation date (wmdr2-bundled.json).
const DATE_PATTERNS = [
  /^\d{4}-\d{2}-\d{2}$/,
  /^\d{4}-\d{2}$/,
  /^\d{4}$/,
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/,
  /^T\d{2}(:\d{2})?(:\d{2})?(?:\.\d+)?Z$/,
];

const pad = (n) => String(n).padStart(2, "0");
const isoDate = (y, m, d) => `${y}-${pad(m)}-${pad(d)}`;
const isValidDate = (y, m, d) => m >= 1 && m <= 12 && d >= 1 && d <= new Date(Date.UTC(y, m, 0)).getUTCDate();

// A date as a spreadsheet program rewrites it when it opens a CSV (Excel
// turns 2026-08-23 into 8/23/2026 or 23.08.2026, by locale): D/M/Y or M/D/Y
// with "/", "." or "-", a two-digit year (Excel's rule: 00-29 is 20xx), an
// optional midnight time; or Y/M/D. Returns YYYY-MM-DD, or null when it
// isn't such a date. When both day/month orders fit (8/7/2026), the one
// that gives `original` wins; otherwise it's ambiguous and null.
export function spreadsheetDateToIso(text, original) {
  const value = (text ?? "").trim().replace(/\s+0?0:00(:00)?$/, "");
  const ymd = value.match(/^(\d{4})[./-](\d{1,2})[./-](\d{1,2})$/);
  if (ymd) {
    const [y, m, d] = ymd.slice(1).map(Number);
    return isValidDate(y, m, d) ? isoDate(y, m, d) : null;
  }
  const parts = value.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{2}|\d{4})$/);
  if (!parts) return null;
  const [a, b] = [Number(parts[1]), Number(parts[2])];
  let y = Number(parts[3]);
  if (parts[3].length === 2) y += y < 30 ? 2000 : 1900;
  const readings = [...new Set([[a, b], [b, a]].filter(([m, d]) => isValidDate(y, m, d)).map(([m, d]) => isoDate(y, m, d)))];
  if (readings.length === 1) return readings[0];
  return readings.find((iso) => iso === original) ?? null;
}

// Short month names in the locales Excel users here are likely to have.
const MONTHS = (() => {
  const names = new Map();
  ["en", "es", "fr", "de", "it", "pt", "nl"].forEach((locale) => {
    const format = new Intl.DateTimeFormat(locale, { month: "short", timeZone: "UTC" });
    for (let m = 1; m <= 12; m++) {
      names.set(format.format(new Date(Date.UTC(2000, m - 1, 1))).toLowerCase().replace(/\.$/, ""), m);
    }
  });
  return names;
})();

// The day and month numbers a value shown as a date has (12-Dec, Dec-12,
// 12/12/2026, 12.12.26), in no particular order, or null.
function shownDateNumbers(text) {
  let parts = text.match(/^(\d{1,2})[-\s]([^\d\s.-]{3,5})\.?(?:[-\s]\d{2,4})?$/);
  if (parts && MONTHS.has(parts[2].toLowerCase())) return [Number(parts[1]), MONTHS.get(parts[2].toLowerCase())];
  parts = text.match(/^([^\d\s.-]{3,5})\.?[-\s](\d{1,2})$/);
  if (parts && MONTHS.has(parts[1].toLowerCase())) return [Number(parts[2]), MONTHS.get(parts[1].toLowerCase())];
  parts = text.match(/^(\d{1,2})[./-](\d{1,2})[./-]\d{2,4}$/);
  return parts ? [Number(parts[1]), Number(parts[2])] : null;
}

// Whether `shown` is how a spreadsheet program rewrites `original` when it
// opens a CSV, rather than an edit: a number with its digits cut
// (3.21321E+11) or leading/trailing zeros dropped, or a text it took for a
// date (12-12 becomes 12-Dec).
export function isSpreadsheetRendering(original, shown) {
  const a = (original ?? "").trim();
  const b = (shown ?? "").trim();
  if (!a || !b || a === b) return false;
  if (isNumber(a) && isNumber(b)) {
    if (Number(a) === Number(b)) return true;
    // Scientific notation keeps as many significant digits as it shows.
    const mantissa = b.match(/^-?(\d+(?:\.\d+)?)e[+-]?\d+$/i);
    if (mantissa) {
      const digits = Math.min(mantissa[1].replace(".", "").length, 15);
      return Number(a).toPrecision(digits) === Number(b).toPrecision(digits);
    }
    // Excel keeps the first 15 digits of a long number and zeroes the rest.
    return /^\d{16,}$/.test(a) && b.length === a.length && b.startsWith(a.slice(0, 15)) && /^0+$/.test(b.slice(15));
  }
  const numbers = a.match(/^(\d{1,2})[-/.](\d{1,2})$/);
  const shownNumbers = numbers && shownDateNumbers(b);
  if (!shownNumbers) return false;
  const sorted = (pair) => [...pair].sort((x, y) => x - y).join(",");
  return sorted([Number(numbers[1]), Number(numbers[2])]) === sorted(shownNumbers);
}

const isNumber = (text) => text.trim() !== "" && !Number.isNaN(Number(text));

// Returns the reason a cell is invalid, or null.
export function cellError(column, text, codelists) {
  const value = (text ?? "").trim();
  if (!value) return column.required ? "Required" : null;
  switch (column.kind) {
    case "number":
      return isNumber(value) ? null : "Must be a number";
    case "numbers":
      return splitList(value).every(isNumber) ? null : `Must be numbers separated by "${LIST_SEPARATOR}"`;
    case "date":
      return DATE_PATTERNS.some((p) => p.test(value)) ? null : "Use YYYY-MM-DD, YYYY-MM, YYYY or a UTC timestamp";
    case "wsi":
      return WIGOS_ID_PATTERN.test(value) ? null : "Not a valid WIGOS identifier";
    case "wsis": {
      const bad = splitList(value).filter((id) => !WIGOS_ID_PATTERN.test(id));
      return bad.length ? `Not a valid WIGOS identifier: ${bad.join(", ")}` : null;
    }
    case "codelist": {
      const options = codelistOptions(column.codelist, codelists);
      // While a codelist is unavailable any notation is accepted.
      return !options.length || findCodelistOption(options, value) ? null : "Not in the codelist";
    }
    default:
      return null;
  }
}

const choiceError = (column, row, value) =>
  !value.trim() ? "Required" : findChoices(column, row, value).length ? null : column.choiceError || "Not one of the choices";

// ---------------------------------------------------------------------------
// Rows

export const isCellChanged = (row, key) => (row.cells[key] ?? "") !== (row.original[key] ?? "");

export const changedColumns = (row, columns) =>
  columns.filter((column) => isEditable(column) && isCellChanged(row, column.key)).map((column) => column.key);

// Value, edit and error state of one cell. `cellStatus(row, column)` may add
// an operation's own { error, hint } (e.g. WIGOS ID availability).
export function cellState(row, column, codelists, cellStatus) {
  const value = row.cells[column.key] ?? "";
  const extra = cellStatus?.(row, column) || {};
  const editable = isCellEditable(column, row);
  return {
    value,
    changed: isEditable(column) && isCellChanged(row, column.key),
    editable,
    error: isEditable(column)
      ? cellError(column, value, codelists) || extra.error || null
      : editable && column.choices
        ? choiceError(column, row, value)
        : null,
    hint: extra.hint || null,
  };
}

// Invalid cells that stop Apply: the ones the user changed, and any cell of
// a new row being added. A stored value that is already invalid (e.g. a
// notation missing from the codelist) is still marked, but doesn't block
// editing the rest.
export function blockingCellCount(columns, rows, codelists, cellStatus) {
  return rows.reduce((count, row) => {
    const sent = row.isNew && changedColumns(row, columns).length > 0;
    return (
      count +
      columns.filter((column) => {
        const state = cellState(row, column, codelists, cellStatus);
        return state.error && (state.changed || sent);
      }).length
    );
  }, 0);
}

export function stationKeys(entry) {
  return { wigos_id: entry.record.id || "", station_name: entry.record.properties?.title || "" };
}

export const observedPropertyLabel = (observation) =>
  observation.observedProperty?.title || conceptCell(observation.observedProperty);

// Other values a file may use for a row's key cells: the observed property
// can be given by its title (as shown), notation or URI.
export const observationAliases = (observation) => ({
  observed_property: [conceptCell(observation.observedProperty), observation.observedProperty?.url].filter(Boolean),
});

// `id` is internal (list keys, selection); files identify rows by their
// key columns instead, see sheetIO.mergeSheet.
export function makeRow(id, stationId, keys, values, extra = {}) {
  const cells = { ...keys, ...values };
  return { id, stationId, cells, original: { ...cells }, ...extra };
}

// Applies the edited rows to copies of the records. `writeRow(record, row,
// changed)` writes a row's changed cells into the record copy. Records
// without edits are returned as they are.
export function applyRowsWith(entries, rows, columns, writeRow) {
  const byStation = new Map();
  rows.forEach((row) => {
    const changed = changedColumns(row, columns);
    if (!changed.length) return;
    if (!byStation.has(row.stationId)) byStation.set(row.stationId, []);
    byStation.get(row.stationId).push({ row, changed });
  });
  return entries.map((entry) => {
    const edits = byStation.get(entry.stationId);
    if (!edits) return entry;
    const record = structuredClone(entry.record);
    edits.forEach(({ row, changed }) => writeRow(record, row, new Set(changed)));
    return { ...entry, record };
  });
}

// Sets `key` on `obj`, or removes it for an empty value.
export function setOrDelete(obj, key, value) {
  const empty = value == null || value === "" || (Array.isArray(value) && !value.length);
  if (empty) delete obj[key];
  else obj[key] = value;
}

// [start, end] with ".." for an open bound, or null when both are empty.
export function datesFromCells(start, end) {
  if (!start && !end) return null;
  return [start || "..", end || ".."];
}

export const dateCell = (value) => (value && value !== ".." ? String(value) : "");

export const toNumber = (text) => (isNumber(text) ? Number(text) : text);

// ---------------------------------------------------------------------------
// Preview and results

const pathSegment = (path, key) => (typeof key === "number" ? `${path}[${key}]` : path ? `${path}.${key}` : key);

// Leaf-level differences between two records: { path, before, after }.
// A value that is missing on one side is undefined there.
export function diffRecord(before, after, path = "") {
  const isObject = (v) => v !== null && typeof v === "object";
  if (!isObject(before) || !isObject(after) || Array.isArray(before) !== Array.isArray(after)) {
    return JSON.stringify(before) === JSON.stringify(after) ? [] : [{ path: path || "record", before, after }];
  }
  // Short arrays of plain values (coordinates, intervals, lists) read better whole.
  if (Array.isArray(before) && [...before, ...after].every((v) => !isObject(v))) {
    return JSON.stringify(before) === JSON.stringify(after) ? [] : [{ path: path || "record", before, after }];
  }
  const keys = Array.isArray(before)
    ? [...Array(Math.max(before.length, after.length)).keys()]
    : [...new Set([...Object.keys(before), ...Object.keys(after)])];
  return keys.flatMap((key) => diffRecord(before[key], after[key], pathSegment(path, key)));
}

export function resultsToCsv(results) {
  return toCsv([
    ["station_id", "station_name", "wigos_id", "status", "message", "errors"],
    ...results.map((r) => [r.station_id, r.station_name ?? "", r.wsi ?? "", r.status, r.message ?? "", (r.errors || []).join(" | ")]),
  ]);
}
