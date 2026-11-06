// Minimal RFC4180 CSV parser: handles quoted fields, escaped quotes ("") and commas within quotes.
// Returns the rows as arrays of fields, blank lines dropped.
export function parseCsvRows(text) {
  text = text.replace(/^﻿/, ""); // Excel writes a BOM in front of UTF-8 CSV

  const rows = [];
  let row = [];
  let field = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const char = text[i];

    if (inQuotes) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        field += char;
      }
      continue;
    }

    if (char === '"') {
      inQuotes = true;
    } else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n" || char === "\r") {
      if (char === "\r" && text[i + 1] === "\n") i++;
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }
  if (field !== "" || row.length) {
    row.push(field);
    rows.push(row);
  }

  return rows.filter((r) => r.length && !(r.length === 1 && r[0] === ""));
}

// Rows as objects keyed by the header row.
export function parseCsv(text) {
  const [header = [], ...body] = parseCsvRows(text);
  return body.map((cells) => Object.fromEntries(header.map((h, i) => [h, cells[i] ?? ""])));
}

const csvField = (value) => {
  const text = value == null ? "" : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
};

// Rows of fields -> CSV text (CRLF line endings, as Excel writes them).
export function toCsv(rows) {
  return rows.map((row) => row.map(csvField).join(",")).join("\r\n") + "\r\n";
}
