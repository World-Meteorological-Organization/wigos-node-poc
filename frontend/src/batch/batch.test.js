import { describe, expect, it } from "vitest";
import * as XLSX from "xlsx";
import * as affiliations from "./affiliations";
import * as configurations from "./configurations";
import * as wigosIds from "./wigosIds";
import { OPERATIONS } from "./operations";
import {
  blockingCellCount,
  cellError,
  cellState,
  diffRecord,
  isCellEditable,
  isSpreadsheetRendering,
  normalizeCell,
  resultsToCsv,
  sameConcept,
  spreadsheetDateToIso,
} from "./common";
import { mergeSheet, pastedTable, sheetTable, workbookTable } from "./sheetIO";
import { parseCsvRows, toCsv } from "../csv";
import { validateWmdrRecord } from "../wmdrSchema";
// examples/0-20008-0-THE.json from wmo-im/wmdr2.
import upstreamExample from "../__fixtures__/upstream-example.json";
// Sets every property defined in schemas/wmdr2-bundled.json.
import allFields from "../__fixtures__/all-fields.json";

const FIXTURES = [
  ["upstream example", upstreamExample],
  ["all-fields record", allFields],
];

const entriesOf = (...records) => records.map((record, i) => ({ stationId: i + 1, record }));

const option = (scheme, code, label) => ({ code, label, id: `http://codes.wmo.int/wmdr/${scheme}/${code}`, description: "" });

const CODELISTS = {
  programAffiliation: [
    option("ProgramAffiliation", "GOS", "WMO Global Observing System"),
    option("ProgramAffiliation", "GBON", "Global Basic Observing Network"),
    option("ProgramAffiliation", "GAWregional", "GAW regional"),
    option("ProgramAffiliation", "GALION", "GALION"),
    option("ProgramAffiliation", "AERONET", "AERONET"),
  ],
  reportingStatus: [option("ReportingStatus", "operational", "Operational"), option("ReportingStatus", "closed", "Closed")],
  operatingStatus: [option("InstrumentOperatingStatus", "operational", "Operational"), option("InstrumentOperatingStatus", "nonOperational", "Non-operational")],
  sourceOfObservation: [option("SourceOfObservation", "automaticReading", "Automatic reading"), option("SourceOfObservation", "manualReading", "Manual reading")],
  observingMethod: [{ label: "Atmosphere", options: [option("ObservingMethodAtmosphere", "78", "Lidar")] }],
  unit: [option("unit", "m", "metre")],
  referenceSurface: [option("ReferenceSurfaceType", "localGroundLevel", "Local ground level")],
};

const columnOf = (module, key) => module.columns.find((column) => column.key === key);
const programme = columnOf(affiliations, "program_affiliation");

const edit = (rows, rowId, cells) => rows.map((row) => (row.id === rowId ? { ...row, cells: { ...row.cells, ...cells } } : row));

describe.each(OPERATIONS.map((operation) => [operation.name, operation.module]))("%s", (_, module) => {
  describe.each(FIXTURES)("with the %s", (__, record) => {
    const entries = entriesOf(record);

    it("returns identical records when nothing is edited", () => {
      const rows = module.toRows(entries);
      expect(module.applyRows(entries, rows, CODELISTS)).toEqual(entries);
      expect(module.applyRows(entries, rows, CODELISTS)[0]).toBe(entries[0]);
    });

    it("has every cell valid when prefilled", () => {
      module.toRows(entries).forEach((row) =>
        module.columns.forEach((column) => expect(cellError(column, row.cells[column.key], CODELISTS)).toBeNull())
      );
    });

    it("round-trips losslessly through CSV and XLSX", () => {
      const rows = module.toRows(entries);
      const table = sheetTable(module.columns, rows);

      const fromCsv = mergeSheet(parseCsvRows(toCsv(table)), module, rows, CODELISTS);
      expect(fromCsv.report).toMatchObject({ matched: rows.length, added: 0, changedCells: 0, unmatched: [], unknownHeaders: [] });
      expect(fromCsv.rows).toEqual(rows);

      const sheet = XLSX.utils.aoa_to_sheet(table.map((r) => r.map((v) => ({ t: "s", v: String(v) }))));
      const book = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(book, sheet, "Batch");
      const reread = XLSX.read(XLSX.write(book, { type: "array", bookType: "xlsx" }));
      const xlsxTable = XLSX.utils.sheet_to_json(reread.Sheets.Batch, { header: 1, raw: false, defval: "" });
      const fromXlsx = mergeSheet(xlsxTable, module, rows, CODELISTS);
      expect(fromXlsx.report.changedCells).toBe(0);
      expect(fromXlsx.rows).toEqual(rows);
    });
  });
});

describe("programme affiliations", () => {
  const entries = entriesOf(upstreamExample);
  const rows = affiliations.toRows(entries);
  const affiliationsOf = (result) => result[0].record.properties.observations[0].programAffiliations;

  it("prefills one row per affiliation from the stored values", () => {
    expect(rows.map((row) => row.id)).toEqual(["1:0:0", "1:0:1", "1:0:2"]);
    expect(rows[1].cells).toMatchObject({
      wigos_id: "0-20008-0-THE",
      observed_property: "12164",
      program_affiliation: "GALION",
      reporting_status: "operational",
      date_start: "2008-01-01",
      date_end: "2024-12-11",
    });
  });

  it("writes edits to the right affiliation and keeps everything else", () => {
    const edited = edit(rows, "1:0:1", { reporting_status: "closed", date_end: "" });
    const result = affiliations.applyRows(entries, edited, CODELISTS);
    const [first, second, third] = affiliationsOf(result);
    expect(second).toEqual({
      dates: ["2008-01-01", ".."],
      programAffiliation: { id: "GALION" },
      reportingStatus: { id: "closed", title: "Closed", url: "http://codes.wmo.int/wmdr/ReportingStatus/closed" },
    });
    expect(first).toEqual(upstreamExample.properties.observations[0].programAffiliations[0]);
    expect(third).toEqual(upstreamExample.properties.observations[0].programAffiliations[2]);
    expect(validateWmdrRecord(result[0].record)).toEqual([]);
    // The input is never mutated.
    expect(upstreamExample.properties.observations[0].programAffiliations[1].reportingStatus).toEqual({ id: "operational" });
  });

  it("adds an affiliation to each observation with a selected row", () => {
    const { rows: withNew, added } = affiliations.addRows(rows, new Set(["1:0:0", "1:0:2"]));
    expect(added.map((row) => row.id)).toEqual(["1:0:new1"]);
    expect(withNew.map((row) => row.id)).toEqual(["1:0:0", "1:0:1", "1:0:2", "1:0:new1"]);
    expect(added[0].cells).toMatchObject({ wigos_id: "0-20008-0-THE", program_affiliation: "" });

    // Left empty, the new row is ignored.
    expect(affiliations.applyRows(entries, withNew, CODELISTS)).toEqual(entries);

    const filled = edit(withNew, "1:0:new1", { program_affiliation: "Global Basic Observing Network", date_start: "2026-01-01" });
    const normalized = filled.map((row) => ({
      ...row,
      cells: { ...row.cells, program_affiliation: normalizeCell(programme, row.cells.program_affiliation, CODELISTS) },
    }));
    const result = affiliationsOf(affiliations.applyRows(entries, normalized, CODELISTS));
    expect(result).toHaveLength(4);
    expect(result[3]).toEqual({
      programAffiliation: { id: "GBON", title: "Global Basic Observing Network", url: "http://codes.wmo.int/wmdr/ProgramAffiliation/GBON" },
      dates: ["2026-01-01", ".."],
    });
  });

  it("locks the programme and start date of existing rows only", () => {
    const { added } = affiliations.addRows(rows, new Set(["1:0:0"]));
    const start = columnOf(affiliations, "date_start");
    expect(isCellEditable(programme, rows[0])).toBe(false);
    expect(isCellEditable(start, rows[0])).toBe(false);
    expect(isCellEditable(columnOf(affiliations, "date_end"), rows[0])).toBe(true);
    expect(isCellEditable(programme, added[0])).toBe(true);
    expect(isCellEditable(start, added[0])).toBe(true);
  });

  it("updates an affiliation with the same programme and start date instead of duplicating it", () => {
    const { rows: withNew } = affiliations.addRows(rows, new Set(["1:0:0"]));
    const filled = edit(withNew, "1:0:new1", { program_affiliation: "AERONET", date_start: "2003-06-01", reporting_status: "closed" });
    const result = affiliationsOf(affiliations.applyRows(entries, filled, CODELISTS));
    expect(result).toHaveLength(3);
    // The end date wasn't filled in on the new row, so the stored one is kept.
    expect(result[2]).toMatchObject({ programAffiliation: { id: "AERONET" }, reportingStatus: { id: "closed" }, dates: ["2003-06-01", "2024-12-11"] });
  });

  it("adds a second period in a programme the observation left", () => {
    const { rows: withNew } = affiliations.addRows(rows, new Set(["1:0:0"]));
    const filled = edit(withNew, "1:0:new1", { program_affiliation: "AERONET", date_start: "2026-01-01" });
    const result = affiliations.applyRows(entries, filled, CODELISTS);
    const list = affiliationsOf(result);
    expect(list).toHaveLength(4);
    expect(list[2].dates).toEqual(["2003-06-01", "2024-12-11"]);
    expect(list[3]).toMatchObject({ programAffiliation: { id: "AERONET" }, dates: ["2026-01-01", ".."] });
    expect(validateWmdrRecord(result[0].record)).toEqual([]);
  });
});

describe("configurations", () => {
  const entries = entriesOf(allFields);
  const rows = configurations.toRows(entries);
  const configurationOf = (result) => result[0].record.properties.observations[0].configurations[0];
  const original = allFields.properties.observations[0].configurations[0];

  it("prefills the stored values", () => {
    expect(rows[0].cells).toMatchObject({
      configuration_id: "c1",
      interval_start: "2020",
      interval_end: "",
      latitude: "46.2",
      longitude: "6.1",
      height: "2",
      vertical_distances: "2;-0.5",
      instrument_manufacturer: "Vaisala",
    });
  });

  it("writes each kind of edit to the right place", () => {
    const edited = edit(rows, rows[0].id, {
      interval_end: "2025-12-31",
      operating_status: "nonOperational",
      instrument_model: "",
      latitude: "47",
      height: "",
      vertical_distances: "10",
    });
    const result = configurations.applyRows(entries, edited, CODELISTS);
    const configuration = configurationOf(result);
    expect(configuration.time).toEqual({ ...original.time, interval: ["2020", "2025-12-31"] });
    expect(configuration.operatingStatus).toMatchObject({ id: "nonOperational" });
    expect(configuration.instrument).toEqual({ id: "i1", manufacturer: "Vaisala" });
    expect(configuration.geometry).toEqual({ type: "Point", coordinates: [6.1, 47] });
    expect(configuration.verticalDistance).toEqual({ ...original.verticalDistance, distances: [10] });
    expect(configuration.sourceOfObservation).toEqual(original.sourceOfObservation);
    expect(validateWmdrRecord(result[0].record)).toEqual([]);
  });

  it("turns a null time into an interval and keeps other time keys", () => {
    const withNullTime = structuredClone(allFields);
    withNullTime.properties.observations[0].configurations[0].time = null;
    const nullEntries = entriesOf(withNullTime);
    const result = configurations.applyRows(nullEntries, edit(configurations.toRows(nullEntries), "1:0:0", { interval_start: "2021" }), CODELISTS);
    expect(configurationOf(result).time).toEqual({ interval: ["2021", ".."] });

    const cleared = configurations.applyRows(entries, edit(rows, "1:0:0", { interval_start: "" }), CODELISTS);
    // all-fields only has an interval, so nothing is left of the time.
    expect(original.time).toEqual({ interval: ["2020", ".."] });
    expect(configurationOf(cleared).time).toBeNull();
  });
});

describe("WIGOS identifiers", () => {
  const manyIds = structuredClone(upstreamExample);
  manyIds.properties.additionalIds = ["0-20008-0-A", "0-20008-0-B", "0-20008-0-C", "0-20008-0-D"];
  const entries = entriesOf(allFields, manyIds);
  const rows = wigosIds.toRows(entries);

  it("shows the current ID read-only, an empty new ID and three additional slots", () => {
    expect(rows.map((row) => row.cells)).toEqual([
      {
        old_wigos_id: "0-20000-0-12345",
        station_name: allFields.properties.title,
        new_wigos_id: "",
        additional_id_1: "0-51-21-2121",
        additional_id_2: "",
        additional_id_3: "",
      },
      {
        old_wigos_id: "0-20008-0-THE",
        station_name: upstreamExample.properties.title,
        new_wigos_id: "",
        additional_id_1: "0-20008-0-A",
        additional_id_2: "0-20008-0-B",
        additional_id_3: "0-20008-0-C",
      },
    ]);
    expect(wigosIds.rowNote(rows[0])).toBeNull();
    expect(wigosIds.rowNote(rows[1])).toMatch(/0-20008-0-D/);
  });

  it("replaces the primary ID only when a new one is entered", () => {
    const [first, second] = wigosIds.applyRows(entries, edit(rows, "1", { new_wigos_id: "0-20000-0-999" }));
    expect(first.record.id).toBe("0-20000-0-999");
    expect(first.record.properties.additionalIds).toEqual(["0-51-21-2121"]);
    expect(second).toBe(entries[1]);
    expect(validateWmdrRecord(first.record)).toEqual([]);
  });

  it("edits the additional IDs in place and keeps the ones beyond the slots", () => {
    const edited = edit(edit(rows, "1", { additional_id_1: "" }), "2", { additional_id_2: "", additional_id_3: "0-20008-0-Z" });
    const [first, second] = wigosIds.applyRows(entries, edited);
    expect(first.record.properties).not.toHaveProperty("additionalIds");
    expect(second.record.id).toBe("0-20008-0-THE");
    expect(second.record.properties.additionalIds).toEqual(["0-20008-0-A", "0-20008-0-Z", "0-20008-0-D"]);
    expect(validateWmdrRecord(first.record)).toEqual([]);
    expect(validateWmdrRecord(second.record)).toEqual([]);
  });

  it("lists own and resulting IDs for the availability check", () => {
    const edited = edit(rows, "1", { new_wigos_id: "0-20000-0-NEW" });
    expect(wigosIds.idsInRows(edited)).toEqual([
      "0-20000-0-NEW", "0-51-21-2121",
      "0-20008-0-THE", "0-20008-0-A", "0-20008-0-B", "0-20008-0-C", "0-20008-0-D",
    ]);
    expect(wigosIds.ownIdsInRows(edited)).toEqual([
      "0-20000-0-12345", "0-51-21-2121",
      "0-20008-0-THE", "0-20008-0-A", "0-20008-0-B", "0-20008-0-C", "0-20008-0-D",
    ]);
  });
});

describe("spreadsheet dates", () => {
  it.each([
    ["8/23/2026", undefined, "2026-08-23"],
    ["23.08.2026", undefined, "2026-08-23"],
    ["23-8-26", undefined, "2026-08-23"],
    ["8/23/2026 0:00", undefined, "2026-08-23"],
    ["2026/8/23", undefined, "2026-08-23"],
    ["8/7/2026", "2026-08-07", "2026-08-07"],
    ["8/7/2026", "2026-07-08", "2026-07-08"],
    ["8/7/2026", "2020-01-01", null],
    ["2/30/2026", undefined, null],
    ["Aug 2026", undefined, null],
  ])("%s (was %s) -> %s", (text, original, expected) => {
    expect(spreadsheetDateToIso(text, original)).toBe(expected);
  });

  it.each([
    ["321321123456", "3.21321E+11", true],
    ["321321123456", "3.21322E+11", false],
    ["1234567890123456789", "1234567890123450000", true],
    ["0042", "42", true],
    ["46.20", "46.2", true],
    ["12-12", "12-Dec", true],
    ["1-2", "2-Jan", true],
    ["3-4", "4-mar", true],
    ["12-12", "dic-12", true],
    ["12-12", "12/12/2026", true],
    ["12-12", "11-Dec", false],
    ["HMP155", "HMP156", false],
    ["", "3.2E+11", false],
  ])("%s shown as %s is a spreadsheet rendering: %s", (original, shown, expected) => {
    expect(isSpreadsheetRendering(original, shown)).toBe(expected);
  });

  it("normalizes date cells, but leaves an ambiguous date for the user to fix", () => {
    const column = { key: "d", kind: "date" };
    expect(normalizeCell(column, "8/23/2026", CODELISTS)).toBe("2026-08-23");
    expect(normalizeCell(column, "8/7/2026", CODELISTS, { original: { d: "2026-07-08" } })).toBe("2026-07-08");
    expect(normalizeCell(column, "8/7/2026", CODELISTS)).toBe("8/7/2026");
    expect(cellError(column, "8/7/2026", CODELISTS)).toMatch(/YYYY-MM-DD/);
    expect(normalizeCell(column, "2026-08", CODELISTS)).toBe("2026-08");
  });
});

describe("cells", () => {
  const status = affiliations.columns.find((c) => c.key === "reporting_status");

  it("accepts a codelist label or notation and flags unknown values", () => {
    expect(normalizeCell(status, " closed ", CODELISTS)).toBe("closed");
    expect(normalizeCell(status, "Closed", CODELISTS)).toBe("closed");
    expect(normalizeCell(status, "Mothballed", CODELISTS)).toBe("Mothballed");
    expect(cellError(status, "Mothballed", CODELISTS)).toBe("Not in the codelist");
    expect(cellError(status, "Mothballed", { reportingStatus: [] })).toBeNull();
  });

  it("checks formats", () => {
    const column = (kind, extra) => ({ key: "x", label: "x", kind, ...extra });
    expect(cellError(column("date"), "2020-01-31")).toBeNull();
    expect(cellError(column("date"), "31/01/2020")).not.toBeNull();
    expect(cellError(column("number"), "1.5")).toBeNull();
    expect(cellError(column("number"), "abc")).not.toBeNull();
    expect(cellError(column("numbers"), "1; -2")).toBeNull();
    expect(cellError(column("wsis"), "0-20000-0-A;nope")).toMatch(/nope/);
    expect(cellError(column("wsi", { required: true }), "")).toBe("Required");
  });

  it("compares concepts on the URI first", () => {
    expect(sameConcept({ id: "12244", url: "a/12244" }, { id: "12244", url: "b/12244" })).toBe(false);
    expect(sameConcept({ id: "GOS" }, { id: "GOS", url: "x/GOS" })).toBe(true);
  });
});

describe("blocking cells for Apply", () => {
  // test_data/test_wmdrv2.json stores "GOS", which isn't in the codelist.
  const stored = structuredClone(upstreamExample);
  stored.properties.observations[0].programAffiliations[0].programAffiliation = { id: "NOT-A-PROGRAMME" };
  const entries = entriesOf(stored);
  const rows = affiliations.toRows(entries);
  const count = (r) => blockingCellCount(affiliations.columns, r, CODELISTS);

  it("doesn't block on an invalid value that was already stored", () => {
    expect(cellError(programme, rows[0].cells.program_affiliation, CODELISTS)).toBe("Not in the codelist");
    expect(count(rows)).toBe(0);
    // Filling another column of that row (e.g. from the fill row) doesn't block either.
    expect(count(edit(rows, "1:0:0", { reporting_status: "closed" }))).toBe(0);
  });

  it("blocks on an invalid edited cell", () => {
    expect(count(edit(rows, "1:0:1", { date_end: "31/12/2024" }))).toBe(1);
  });

  it("blocks on a new row missing its programme, but not on an empty new row", () => {
    const { rows: withNew } = affiliations.addRows(rows, new Set(["1:0:0"]));
    expect(count(withNew)).toBe(0);
    expect(count(edit(withNew, "1:0:new1", { reporting_status: "closed" }))).toBe(1);
  });
});

describe("import", () => {
  const entries = entriesOf(upstreamExample);
  const rows = affiliations.toRows(entries);
  const header = ["wigos_id", "station_name", "observed_property", "Programme/network", "From", "Reporting status", "colour"];

  it("matches rows on WIGOS ID, observed property, programme and start, and reports the rest", () => {
    const table = [
      header,
      ["0-20008-0-THE", "renamed in Excel", "12164", "GALION", "2008-01-01", "Closed", "red"],
      ["0-20008-0-XXX", "", "12164", "GALION", "2008-01-01", "closed", ""],
      ["", "", "", "", "", "", ""],
    ];
    const { rows: next, report } = mergeSheet(table, affiliations, rows, CODELISTS);
    expect(report).toEqual({
      matched: 1,
      added: 0,
      changedCells: 1,
      restored: 0,
      unmatched: ["0-20008-0-XXX / 12164 / GALION"],
      unknownHeaders: ["colour"],
      error: null,
    });
    expect(next[1].cells.reporting_status).toBe("closed");
    expect(next[1].cells.station_name).toBe(rows[1].cells.station_name);
    expect(next).toHaveLength(rows.length);
  });

  it("adds a row for a programme period the observation doesn't have yet", () => {
    const table = [header, ["0-20008-0-THE", "", "12164", "GBON", "2026-01-01", "operational", ""]];
    const { rows: next, report } = mergeSheet(table, affiliations, rows, CODELISTS);
    expect(report).toMatchObject({ matched: 0, added: 1, unmatched: [] });
    expect(next).toHaveLength(rows.length + 1);
    expect(next[3]).toMatchObject({
      isNew: true,
      cells: { program_affiliation: "GBON", date_start: "2026-01-01", reporting_status: "operational" },
    });
    const result = affiliations.applyRows(entries, next, CODELISTS)[0].record.properties.observations[0].programAffiliations;
    expect(result).toHaveLength(4);
    expect(result[3]).toMatchObject({ programAffiliation: { id: "GBON" }, dates: ["2026-01-01", ".."] });
  });

  it("matches pasted whole rows like an import: edits existing rows, adds new programme periods", () => {
    const line = (cells) => affiliations.columns.map((column) => cells[column.key] ?? "").join("\t");
    const text = `${[
      line({ ...rows[1].cells, station_name: "renamed", reporting_status: "closed" }),
      line({ ...rows[1].cells, program_affiliation: "GBON", date_start: "2026-01-01", date_end: "" }),
    ].join("\r\n")}\r\n`;
    const { rows: next, report } = mergeSheet(pastedTable(text, affiliations), affiliations, rows, CODELISTS);

    expect(report).toMatchObject({ matched: 1, added: 1, changedCells: 1, unmatched: [] });
    expect(next[1].cells).toEqual({ ...rows[1].cells, reporting_status: "closed" });
    expect(next[3]).toMatchObject({
      isNew: true,
      cells: { program_affiliation: "GBON", date_start: "2026-01-01", reporting_status: "operational", date_end: "" },
    });
  });

  it("takes a pasted block with a header naming the key columns as whole rows", () => {
    const text = "wigos_id\tobserved_property\tProgramme/network\tFrom\tReporting status\n0-20008-0-THE\t12164\tGALION\t2008-01-01\tclosed";
    const { rows: next, report } = mergeSheet(pastedTable(text, affiliations), affiliations, rows, CODELISTS);
    expect(report).toMatchObject({ matched: 1, changedCells: 1 });
    expect(next[1].cells.reporting_status).toBe("closed");
  });

  it("leaves a partial pasted block to the cell-by-cell paste", () => {
    expect(pastedTable("closed\t2030-01-01\nclosed\t", affiliations)).toBeNull();
    expect(pastedTable("x\ty\tz", { columns: [{ key: "x", label: "X" }, { key: "y", label: "Y" }, { key: "z", label: "Z" }] })).toBeNull();
  });

  it("identifies a row by WIGOS ID, observed property and programme; the locked start date isn't changed", () => {
    const table = [header, ["0-20008-0-THE", "", "12164", "GALION", "2030-01-01", "closed", ""]];
    const { rows: next, report } = mergeSheet(table, affiliations, rows, CODELISTS);
    expect(report).toMatchObject({ matched: 1, added: 0, changedCells: 1, unmatched: [] });
    expect(next[1].cells).toEqual({ ...rows[1].cells, reporting_status: "closed" });
  });

  it("picks between periods of one programme by start date, and adds a period that matches none", () => {
    const record = structuredClone(upstreamExample);
    const [, galion] = record.properties.observations[0].programAffiliations;
    record.properties.observations[0].programAffiliations.push({ ...galion, dates: ["2025-01-01", ".."] });
    const periodRows = affiliations.toRows(entriesOf(record));
    const table = [
      header,
      ["0-20008-0-THE", "", "12164", "GALION", "2025-01-01", "closed", ""],
      ["0-20008-0-THE", "", "12164", "GALION", "2030-01-01", "operational", ""],
    ];
    const { rows: next, report } = mergeSheet(table, affiliations, periodRows, CODELISTS);
    expect(report).toMatchObject({ matched: 1, added: 1, unmatched: [] });
    expect(next[3].cells).toMatchObject({ date_start: "2025-01-01", reporting_status: "closed" });
    expect(next[1].cells).toEqual(periodRows[1].cells);
    expect(next[4]).toMatchObject({ isNew: true, cells: { program_affiliation: "GALION", date_start: "2030-01-01" } });
  });

  it("adds rows only to the station's own observations, never a new observation", () => {
    const record = structuredClone(upstreamExample);
    record.properties.observations.push({
      ...structuredClone(record.properties.observations[0]),
      observedProperty: { id: "224", title: "Air temperature" },
      programAffiliations: [{ programAffiliation: { id: "GOS" }, dates: ["2020-01-01", ".."] }],
    });
    const twoEntries = entriesOf(record);
    const twoRows = affiliations.toRows(twoEntries);
    const table = [
      header,
      // By notation; the grid shows the title.
      ["0-20008-0-THE", "", "224", "GBON", "2026-01-01", "operational", ""],
      ["0-20008-0-THE", "", "999", "GBON", "2026-01-01", "operational", ""],
    ];
    const { rows: next, report } = mergeSheet(table, affiliations, twoRows, CODELISTS);
    expect(report).toMatchObject({ matched: 0, added: 1, unmatched: ["0-20008-0-THE / 999 / GBON (not an observation of this station)"] });
    expect(next.map((row) => row.cells.observed_property)).toEqual(["12164", "12164", "12164", "Air temperature", "Air temperature"]);
    expect(next[4]).toMatchObject({ isNew: true, obsIndex: 1 });

    const result = affiliations.applyRows(twoEntries, next, CODELISTS)[0].record.properties.observations;
    expect(result).toHaveLength(2);
    expect(result[1].programAffiliations.map((a) => a.programAffiliation.id)).toEqual(["GOS", "GBON"]);
  });

  it("lets an added row move to another observation of the station only", () => {
    const record = structuredClone(upstreamExample);
    record.properties.observations.push({ ...structuredClone(record.properties.observations[0]), observedProperty: { id: "224" } });
    const { added } = affiliations.addRows(affiliations.toRows(entriesOf(record)), new Set(["1:0:0"]));
    const property = columnOf(affiliations, "observed_property");

    expect(isCellEditable(property, rows[0])).toBe(false);
    expect(isCellEditable(property, added[0])).toBe(true);
    expect(property.choices(added[0]).map((choice) => choice.label)).toEqual(["12164", "224"]);

    const moved = affiliations.syncNewRow({ ...added[0], cells: { ...added[0].cells, observed_property: "224" } });
    expect(moved.obsIndex).toBe(1);
    expect(affiliations.syncNewRow({ ...added[0], cells: { ...added[0].cells, observed_property: "999" } })).toBeNull();
    expect(cellState({ ...added[0], cells: { ...added[0].cells, observed_property: "999" } }, property, CODELISTS).error).toBe(
      "Not an observation of this station"
    );
  });

  it("reads dates back that Excel rewrote in a CSV, keeping unchanged ones as they were", () => {
    const record = structuredClone(allFields);
    record.properties.observations[0].configurations[0].time.interval = ["2026-08-07", ".."];
    const cfgRows = configurations.toRows(entriesOf(record));
    const table = sheetTable(configurations.columns, cfgRows);
    const start = table[0].indexOf("interval_start");
    const end = table[0].indexOf("interval_end");
    // As Excel saves them (US format): the unchanged start, which could also
    // read as 8 July, and the one date the user edited.
    table[1][start] = "8/7/2026";
    table[1][end] = "8/23/2026";
    const { rows: next, report } = mergeSheet(parseCsvRows(toCsv(table)), configurations, cfgRows, CODELISTS);
    expect(report).toMatchObject({ matched: cfgRows.length, changedCells: 1 });
    expect(next[0].cells.interval_start).toBe("2026-08-07");
    expect(next[0].cells.interval_end).toBe("2026-08-23");
  });

  it("keeps values Excel reformatted in a CSV, and still takes real edits", () => {
    const record = structuredClone(allFields);
    const configuration = record.properties.observations[0].configurations[0];
    configuration.instrument = { ...configuration.instrument, id: "321321123456", model: "12-12" };
    const cfgRows = configurations.toRows(entriesOf(record));
    const table = sheetTable(configurations.columns, cfgRows);
    const col = (key) => table[0].indexOf(key);
    table[1][col("instrument_id")] = "3.21321E+11";
    table[1][col("instrument_model")] = "12-Dec";
    table[1][col("instrument_manufacturer")] = "SUTRON";
    const { rows: next, report } = mergeSheet(parseCsvRows(toCsv(table)), configurations, cfgRows, CODELISTS);

    expect(report).toMatchObject({ changedCells: 1, restored: 2 });
    expect(next[0].cells).toMatchObject({ instrument_id: "321321123456", instrument_model: "12-12", instrument_manufacturer: "SUTRON" });
  });

  it("reads Excel date cells as ISO dates", () => {
    const serial = (Date.UTC(2026, 7, 23) - Date.UTC(1899, 11, 30)) / 86400000;
    const sheet = XLSX.utils.aoa_to_sheet([["From"], [{ t: "n", v: serial, z: "m/d/yy" }], [{ t: "n", v: serial + 0.5, z: "m/d/yy h:mm" }], ["text"]]);
    const book = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(book, sheet, "Batch");
    const reread = XLSX.read(XLSX.write(book, { type: "array", bookType: "xlsx" }), { cellNF: true });
    expect(workbookTable(XLSX, reread)).toEqual([["From"], ["2026-08-23"], ["2026-08-23T12:00:00Z"], ["text"]]);
  });

  it("needs the key columns", () => {
    const { rows: next, report } = mergeSheet([["wigos_id", "Reporting status"], ["0-20008-0-THE", "closed"]], affiliations, rows, CODELISTS);
    expect(report.error).toMatch(/observed_property/);
    expect(next).toBe(rows);
  });

  it("matches WIGOS ID rows on the current ID", () => {
    const idEntries = entriesOf(upstreamExample);
    const idRows = wigosIds.toRows(idEntries);
    const { rows: next, report } = mergeSheet(
      [["old_wigos_id", "new_wigos_id"], ["0-20008-0-THE", "0-20008-0-NEW"]],
      wigosIds,
      idRows,
      CODELISTS
    );
    expect(report).toMatchObject({ matched: 1, changedCells: 1 });
    expect(wigosIds.applyRows(idEntries, next)[0].record.id).toBe("0-20008-0-NEW");
  });
});

describe("diffRecord and results", () => {
  it("lists leaf changes with readable paths", () => {
    const before = { id: "a", properties: { list: [{ x: 1 }, { x: 2 }], dates: ["2020", ".."] } };
    const after = { id: "a", properties: { list: [{ x: 1 }, { x: 3 }, { x: 4 }], dates: ["2020", "2021"] } };
    expect(diffRecord(before, after)).toEqual([
      { path: "properties.list[1].x", before: 2, after: 3 },
      { path: "properties.list[2]", before: undefined, after: { x: 4 } },
      { path: "properties.dates", before: ["2020", ".."], after: ["2020", "2021"] },
    ]);
  });

  it("writes results as CSV", () => {
    const csv = resultsToCsv([{ station_id: 1, station_name: "A, B", wsi: "0-1-0-a", status: "error", message: "bad", errors: ["e1", "e2"] }]);
    expect(parseCsvRows(csv)[1]).toEqual(["1", "A, B", "0-1-0-a", "error", "bad", "e1 | e2"]);
  });
});
