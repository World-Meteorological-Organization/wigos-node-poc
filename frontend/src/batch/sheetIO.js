import { parseCsvRows, toCsv } from "../csv";
import { isCellEditable, isEditable, isSpreadsheetRendering, normalizeCell } from "./common";

// CSV / Excel export and import of a batch grid. Files have one column per
// grid column, headed by the column key. Import updates the grid rows it
// matches on the operation's key columns (see mergeSheet); it never adds
// stations, observations or configurations.

// SheetJS is only downloaded when a user exports or imports an Excel file.
const loadXlsx = () => import("xlsx");

export function sheetTable(columns, rows) {
  return [columns.map((column) => column.key), ...rows.map((row) => columns.map((column) => row.cells[column.key] ?? ""))];
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

// The BOM makes Excel open the CSV as UTF-8.
export const csvBlob = (text) => new Blob(["﻿", text], { type: "text/csv;charset=utf-8" });

export async function exportSheet(columns, rows, format, basename) {
  const table = sheetTable(columns, rows);
  if (format === "csv") {
    downloadBlob(csvBlob(toCsv(table)), `${basename}.csv`);
    return;
  }
  const XLSX = await loadXlsx();
  // Every cell is written as text so Excel doesn't turn IDs or dates into numbers.
  const sheet = XLSX.utils.aoa_to_sheet(table.map((row) => row.map((value) => ({ t: "s", v: String(value) }))));
  sheet["!cols"] = columns.map((column) => ({ wch: Math.max(10, Math.round((column.width || 140) / 7)) }));
  const book = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(book, sheet, "Batch");
  XLSX.writeFile(book, `${basename}.xlsx`);
}

// File -> rows of strings (first sheet for Excel files).
export async function readSheet(file) {
  if (/\.csv$/i.test(file.name) || file.type === "text/csv") {
    return parseCsvRows(await file.text());
  }
  const XLSX = await loadXlsx();
  return workbookTable(XLSX, XLSX.read(await file.arrayBuffer(), { cellNF: true }));
}

// The first sheet of a workbook read with `cellNF` (number formats) as rows
// of strings. Cells are taken as Excel shows them, except dates: a value
// typed into a cell becomes a date cell shown in the local format
// (8/23/26), so dates are written as YYYY-MM-DD (with a UTC time, if any).
export function workbookTable(XLSX, book) {
  const sheet = book.Sheets[book.SheetNames[0]];
  Object.keys(sheet).forEach((address) => {
    const cell = sheet[address];
    if (address.startsWith("!") || cell.t !== "n" || !cell.z || !XLSX.SSF.is_date(cell.z)) return;
    const { y, m, d, H, M, S } = XLSX.SSF.parse_date_code(cell.v);
    const pad = (n) => String(n).padStart(2, "0");
    const date = `${y}-${pad(m)}-${pad(d)}`;
    cell.w = H || M || S ? `${date}T${pad(H)}:${pad(M)}:${pad(S)}Z` : date;
  });
  return XLSX.utils.sheet_to_json(sheet, { header: 1, raw: false, defval: "" }).map((row) => row.map(String));
}

// Applies an imported table to the grid rows. `sheet` is the operation
// module: its `columns`, the `importKeys` that identify a row, optionally
// `importPreferKeys` that pick one of several matching rows, and optionally
// `importParentKeys` + `newRowFor` (+ `syncNewRow`) to add rows
// (affiliations: a programme an observation of the station doesn't have
// yet). Headers may be column keys or labels. Returns the updated rows and a
// report:
//   { matched, added, changedCells, restored, unmatched: [descriptions], unknownHeaders, error }
// `restored` counts cells a spreadsheet program had rewritten (see
// isSpreadsheetRendering) that kept their value.
export function mergeSheet(table, sheet, rows, codelists) {
  const { columns, importKeys, importPreferKeys = [], importParentKeys, newRowFor, syncNewRow } = sheet;
  const [header = [], ...body] = table;
  const byName = new Map();
  columns.forEach((column) => {
    byName.set(column.key.toLowerCase(), column);
    byName.set(column.label.toLowerCase(), column);
  });
  const fileColumns = header.map((name) => byName.get(String(name).trim().toLowerCase()) || null);
  const report = {
    matched: 0,
    added: 0,
    changedCells: 0,
    restored: 0,
    unmatched: [],
    unknownHeaders: header.filter((name, i) => String(name).trim() && !fileColumns[i]).map(String),
    error: null,
  };

  const columnOf = (key) => columns.find((column) => column.key === key);
  const indexOf = (key) => fileColumns.findIndex((column) => column?.key === key);
  const missing = importKeys.filter((key) => indexOf(key) < 0);
  if (missing.length) {
    const names = missing.map((key) => `"${key}"`).join(", ");
    return { rows, report: { ...report, error: `The file needs the ${names} ${missing.length === 1 ? "column" : "columns"} to match its rows to the grid.` } };
  }

  // Keys compare trimmed and case-insensitively; codelist keys by notation.
  const keyValue = (key, raw) => {
    const column = columnOf(key);
    const value = column.kind === "codelist" ? normalizeCell(column, raw, codelists) : raw;
    return String(value ?? "").trim().toLowerCase();
  };
  const rowHas = (row, key, fileValue) =>
    [row.cells[key], ...(row.aliases?.[key] || [])].some((candidate) => keyValue(key, candidate) === fileValue);
  const allMatching = (keys, fileKeys) => rows.filter((row) => keys.every((key) => rowHas(row, key, fileKeys[key])));
  // One row: the only match, or the one the prefer keys also match. Several
  // matches and none preferred is no match (e.g. a new programme period).
  const preferKeys = importPreferKeys.filter((key) => indexOf(key) >= 0);
  const matching = (fileKeys) => {
    const found = allMatching(importKeys, fileKeys);
    if (found.length <= 1 || !preferKeys.length) return found[0] || null;
    return allMatching(preferKeys, fileKeys).find((row) => found.includes(row)) || null;
  };
  const indexedKeys = [...importKeys, ...preferKeys];
  const describe = (cells, line) =>
    importKeys.map((key) => String(cells[indexOf(key)] ?? "").trim()).filter(Boolean).join(" / ") || `line ${line + 2}`;

  const updates = new Map(); // row id -> raw values
  const additions = []; // { template, values, description }
  body.forEach((cells, line) => {
    if (cells.every((cell) => !String(cell ?? "").trim())) return;
    const fileKeys = Object.fromEntries(indexedKeys.map((key) => [key, keyValue(key, cells[indexOf(key)])]));
    // Raw values; normalized per row, as some depend on the row.
    const values = {};
    fileColumns.forEach((column, i) => {
      if (column && (isEditable(column) || column.choices)) values[column.key] = cells[i];
    });

    const row = matching(fileKeys);
    if (row) {
      updates.set(row.id, values);
      return;
    }
    const template = importParentKeys && newRowFor && allMatching(importParentKeys, fileKeys)[0];
    if (template) {
      additions.push({ template, values, description: describe(cells, line) });
      return;
    }
    report.unmatched.push(describe(cells, line));
  });

  // Only the cells a row allows are written (e.g. not an existing
  // affiliation's programme or start date).
  const writable = (row, values) =>
    Object.fromEntries(
      Object.entries(values)
        .filter(([key]) => isCellEditable(columnOf(key), row))
        .map(([key, value]) => [key, normalizeCell(columnOf(key), value, codelists, row)])
    );

  // A value a spreadsheet program rewrote (12-12 shown as 12-Dec) keeps the
  // cell's value; dates and codelists are normalized on their own.
  const unspoiled = (row, values) =>
    Object.fromEntries(
      Object.entries(values).map(([key, value]) => {
        const kind = columnOf(key).kind;
        if (kind === "date" || kind === "codelist" || !isSpreadsheetRendering(row.cells[key], value)) return [key, value];
        report.restored += 1;
        return [key, row.cells[key]];
      })
    );

  let next = rows.map((row) => {
    if (!updates.has(row.id)) return row;
    report.matched += 1;
    const values = unspoiled(row, writable(row, updates.get(row.id)));
    const changed = Object.keys(values).filter((key) => values[key] !== (row.cells[key] ?? ""));
    report.changedCells += changed.length;
    return changed.length ? { ...row, cells: { ...row.cells, ...values } } : row;
  });

  // New rows go after the last row of the same observation, or else of the
  // same station. One whose observed property the station doesn't have is
  // left out: this grid never adds observations.
  additions.forEach(({ template, values, description }) => {
    const row = newRowFor(template, next);
    let filled = { ...row, cells: { ...row.cells, ...writable(row, values) } };
    if (syncNewRow) filled = syncNewRow(filled);
    if (!filled) {
      report.unmatched.push(`${description} (not an observation of this station)`);
      return;
    }
    const lastOf = (same) => next.reduce((index, r, i) => (same(r) ? i : index), -1);
    const sameStation = (r) => r.stationId === filled.stationId;
    const sameObservation = lastOf((r) => sameStation(r) && r.obsIndex === filled.obsIndex);
    const last = sameObservation >= 0 ? sameObservation : lastOf(sameStation);
    next = [...next.slice(0, last + 1), filled, ...next.slice(last + 1)];
    report.added += 1;
  });

  return { rows: next, report };
}

// A block pasted into the grid, as a table for mergeSheet when it holds
// whole rows: its first line names the key columns (copied with the header
// of an export), or every line has one value per grid column, in grid order
// (rows copied from the grid or an export). Such rows are matched like an
// import, so only editable cells change and an unknown programme period
// becomes a new row. Returns null for any other block, which is pasted
// cell by cell from the active cell instead.
export function pastedTable(text, sheet) {
  const lines = text.replace(/\r?\n$/, "").split(/\r?\n/).map((line) => line.split("\t"));
  const { columns, importKeys = [] } = sheet;
  if (!importKeys.length) return null;
  const header = new Set(lines[0].map((cell) => cell.trim().toLowerCase()));
  const named = (key) => {
    const column = columns.find((col) => col.key === key);
    return header.has(key.toLowerCase()) || header.has(column.label.toLowerCase());
  };
  if (importKeys.every(named)) return lines;
  if (lines.every((cells) => cells.length === columns.length)) return [columns.map((column) => column.key), ...lines];
  return null;
}
