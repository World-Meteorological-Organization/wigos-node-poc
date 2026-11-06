import {
  KEY_COLUMNS,
  applyRowsWith,
  conceptCell,
  conceptForCell,
  dateCell,
  datesFromCells,
  findChoices,
  makeRow,
  observationAliases,
  observedPropertyLabel,
  sameConcept,
  setOrDelete,
  stationKeys,
} from "./common";
import { codelistOptions } from "../codelists";

// Programme affiliations: one row per affiliation of one observation.
//
// A row is identified by the station's WIGOS ID, the observed property and
// the programme. The start date only tells apart the periods of a programme
// the observation left and joined again. Programme and start date are
// locked on existing rows and only set on rows being added.
//
// Added rows can move to another observation of the same station (the
// observed property is a dropdown of the station's observations), but this
// grid never adds observations: one made from an affiliation row would have
// no configuration, which makes the record invalid.

const observedProperty = {
  ...KEY_COLUMNS.observedProperty,
  // The station's observations, for an added row.
  choices: (row) => row.observationChoices || [],
  choiceError: "Not an observation of this station",
};

export const columns = [
  KEY_COLUMNS.wigosId,
  KEY_COLUMNS.stationName,
  observedProperty,
  {
    key: "program_affiliation",
    label: "Programme/network",
    kind: "codelist",
    codelist: "programAffiliation",
    required: true,
    lockedOnExisting: true,
    width: 200,
  },
  { key: "date_start", label: "From", kind: "date", lockedOnExisting: true, width: 120 },
  { key: "reporting_status", label: "Reporting status", kind: "codelist", codelist: "reportingStatus", width: 170 },
  { key: "date_end", label: "To (empty if ongoing)", kind: "date", width: 120 },
];

// A file row is matched to a grid row on these columns; when several rows
// match (periods of one programme), the start date picks one. A row of a
// known station that matches none becomes a new affiliation, if its observed
// property is one of the station's observations (see sheetIO.mergeSheet).
export const importKeys = ["wigos_id", "observed_property", "program_affiliation"];
export const importPreferKeys = ["date_start"];
export const importParentKeys = ["wigos_id"];

const observationsOf = (record) => record.properties?.observations || [];

function observationChoicesOf(record) {
  return observationsOf(record).map((observation, obsIndex) => ({
    obsIndex,
    label: observedPropertyLabel(observation),
    aliases: observationAliases(observation).observed_property,
  }));
}

function affiliationCells(affiliation) {
  const [start, end] = affiliation?.dates || [];
  return {
    program_affiliation: conceptCell(affiliation?.programAffiliation),
    reporting_status: conceptCell(affiliation?.reportingStatus),
    date_start: dateCell(start),
    date_end: dateCell(end),
  };
}

export function toRows(entries) {
  return entries.flatMap((entry) => {
    const station = stationKeys(entry);
    const observationChoices = observationChoicesOf(entry.record);
    return observationsOf(entry.record).flatMap((observation, obsIndex) => {
      const keys = { ...station, observed_property: observedPropertyLabel(observation) };
      return (observation.programAffiliations || []).map((affiliation, itemIndex) =>
        makeRow(`${entry.stationId}:${obsIndex}:${itemIndex}`, entry.stationId, keys, affiliationCells(affiliation), {
          obsIndex,
          itemIndex,
          aliases: observationAliases(observation),
          observationChoices,
        })
      );
    });
  });
}

const obsKey = (row) => `${row.stationId}:${row.obsIndex}`;

// An empty affiliation row for the observation of `template`.
export function newRowFor(template, rows) {
  // Counted per station: an added row may move to another observation.
  const n = rows.filter((r) => r.isNew && r.stationId === template.stationId).length + 1;
  const { wigos_id, station_name, observed_property } = template.cells;
  return makeRow(`${obsKey(template)}:new${n}`, template.stationId, { wigos_id, station_name, observed_property }, affiliationCells(null), {
    obsIndex: template.obsIndex,
    itemIndex: null,
    isNew: true,
    aliases: template.aliases,
    observationChoices: template.observationChoices,
  });
}

// Points an added row at the observation its observed property cell names
// (its own one first, when two observations share a label). Returns null
// when the station has no such observation.
export function syncNewRow(row) {
  const matches = findChoices(observedProperty, row, row.cells.observed_property);
  const choice = matches.find((c) => c.obsIndex === row.obsIndex) || matches[0];
  if (!choice) return null;
  return { ...row, obsIndex: choice.obsIndex, aliases: { observed_property: choice.aliases } };
}

// Adds an empty affiliation row under each observation that has a selected
// row, right after that observation's last row. A row left empty is ignored.
export function addRows(rows, selectedIds) {
  const targets = new Map();
  rows.forEach((row) => {
    if (selectedIds.has(row.id)) targets.set(obsKey(row), row);
  });
  if (!targets.size) return { rows, added: [] };

  const lastIndex = new Map(rows.map((row, i) => [obsKey(row), i]));
  const added = [];
  const next = [];
  rows.forEach((row, i) => {
    next.push(row);
    const key = obsKey(row);
    if (!targets.has(key) || lastIndex.get(key) !== i) return;
    const newRow = newRowFor(targets.get(key), [...rows, ...added]);
    added.push(newRow);
    next.push(newRow);
  });
  return { rows: next, added };
}

function writeAffiliation(target, row, changed, codelists) {
  if (changed.has("program_affiliation")) {
    const options = codelistOptions("programAffiliation", codelists);
    setOrDelete(target, "programAffiliation", conceptForCell(row.cells.program_affiliation, options, target.programAffiliation));
  }
  if (changed.has("reporting_status")) {
    const options = codelistOptions("reportingStatus", codelists);
    setOrDelete(target, "reportingStatus", conceptForCell(row.cells.reporting_status, options, target.reportingStatus));
  }
  if (changed.has("date_start") || changed.has("date_end")) {
    setOrDelete(target, "dates", datesFromCells(row.cells.date_start, row.cells.date_end));
  }
}

const startOf = (affiliation) => dateCell(affiliation.dates?.[0]);

export function applyRows(entries, rows, codelists) {
  return applyRowsWith(entries, rows, columns, (record, row, changed) => {
    const observation = observationsOf(record)[row.obsIndex];
    if (!observation) return;
    observation.programAffiliations = observation.programAffiliations || [];
    if (!row.isNew) {
      writeAffiliation(observation.programAffiliations[row.itemIndex], row, changed, codelists);
      return;
    }
    // A new row with the programme and start date of an existing affiliation
    // updates it instead of adding a duplicate; any other start date is a
    // separate period in the programme.
    const concept = conceptForCell(row.cells.program_affiliation, codelistOptions("programAffiliation", codelists));
    const existing =
      concept &&
      observation.programAffiliations.find(
        (a) => sameConcept(a.programAffiliation, concept) && startOf(a) === (row.cells.date_start || "")
      );
    if (existing) {
      // Programme and start already match; only what else was filled in is written.
      const rest = new Set([...changed].filter((key) => key !== "program_affiliation" && key !== "date_start"));
      writeAffiliation(existing, row, rest, codelists);
    } else {
      const affiliation = {};
      writeAffiliation(affiliation, row, changed, codelists);
      observation.programAffiliations.push(affiliation);
    }
  });
}
