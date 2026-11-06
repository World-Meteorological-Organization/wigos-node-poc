import * as affiliations from "./affiliations";
import * as configurations from "./configurations";
import * as wigosIds from "./wigosIds";

// The batch operations offered in the wizard, in the order they are listed.
// Each module exports `columns`, `toRows(entries)` and
// `applyRows(entries, rows, codelists)`; `addRows` is optional.
export const OPERATIONS = [
  {
    id: "affiliations",
    name: "Programme affiliations",
    description: "Change programme/network affiliations, their reporting status and dates, or add an affiliation to observations.",
    rowLabel: "One row per affiliation of an observation",
    module: affiliations,
  },
  {
    id: "configurations",
    name: "Configurations",
    description: "Change interval, operating status, source, observing method, instrument, location and vertical distance of configurations.",
    rowLabel: "One row per configuration of an observation",
    module: configurations,
  },
  {
    id: "wigosIds",
    name: "WIGOS identifiers",
    description: "Give stations a new primary WIGOS identifier and edit up to three additional identifiers.",
    rowLabel: "One row per station",
    module: wigosIds,
  },
];

export const operationById = (id) => OPERATIONS.find((operation) => operation.id === id);

// Codelists an operation's columns need.
export const codelistsOf = (operation) => [
  ...new Set(operation.module.columns.filter((column) => column.codelist).map((column) => column.codelist)),
];
