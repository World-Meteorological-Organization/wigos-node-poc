import {
  KEY_COLUMNS,
  applyRowsWith,
  conceptCell,
  conceptForCell,
  dateCell,
  datesFromCells,
  joinList,
  makeRow,
  observationAliases,
  observedPropertyLabel,
  setOrDelete,
  splitList,
  stationKeys,
  toNumber,
} from "./common";
import { codelistOptions } from "../codelists";

// Configurations (the WMDR2 equivalent of OSCAR's "change schedule"): one
// row per existing configuration of one observation.

// Codelist columns: grid column -> configuration key and codelist name.
const CONCEPT_COLUMNS = {
  operating_status: { field: "operatingStatus", codelist: "operatingStatus" },
  source_of_observation: { field: "sourceOfObservation", codelist: "sourceOfObservation" },
  observing_method: { field: "observingMethod", codelist: "observingMethod" },
};

const INSTRUMENT_COLUMNS = {
  instrument_id: "id",
  instrument_manufacturer: "manufacturer",
  instrument_model: "model",
};

export const columns = [
  KEY_COLUMNS.wigosId,
  KEY_COLUMNS.stationName,
  KEY_COLUMNS.observedProperty,
  { key: "configuration_id", label: "Configuration ID", kind: "key", width: 140 },
  { key: "interval_start", label: "Interval start", kind: "date", width: 120 },
  { key: "interval_end", label: "Interval end (empty if ongoing)", kind: "date", width: 130 },
  { key: "operating_status", label: "Operating status", kind: "codelist", codelist: "operatingStatus", width: 170 },
  { key: "source_of_observation", label: "Source of observation", kind: "codelist", codelist: "sourceOfObservation", width: 180 },
  { key: "observing_method", label: "Observing method", kind: "codelist", codelist: "observingMethod", width: 200 },
  { key: "instrument_id", label: "Instrument ID", kind: "text", width: 140 },
  { key: "instrument_manufacturer", label: "Manufacturer", kind: "text", width: 140 },
  { key: "instrument_model", label: "Model", kind: "text", width: 120 },
  { key: "instrument_serial_number", label: "Serial number", kind: "text", width: 130 },
  { key: "latitude", label: "Latitude", kind: "number", width: 100 },
  { key: "longitude", label: "Longitude", kind: "number", width: 100 },
  { key: "height", label: "Height (m)", kind: "number", width: 100 },
  { key: "vertical_distances", label: "Vertical distances", kind: "numbers", width: 130 },
  { key: "vertical_unit", label: "Vertical unit", kind: "codelist", codelist: "unit", width: 130 },
  { key: "reference_surface", label: "Reference surface", kind: "codelist", codelist: "referenceSurface", width: 170 },
];

// A file row is matched to a grid row on these columns.
export const importKeys = ["wigos_id", "observed_property", "configuration_id"];

const observationsOf = (record) => record.properties?.observations || [];
const text = (value) => (value != null ? String(value) : "");

function configurationCells(configuration) {
  const [start, end] = configuration.time?.interval || [];
  const [longitude, latitude, height] = configuration.geometry?.coordinates || [];
  const cells = {
    configuration_id: text(configuration.id),
    interval_start: dateCell(start),
    interval_end: dateCell(end),
    instrument_serial_number: text(configuration.instrumentSerialNumber),
    latitude: text(latitude),
    longitude: text(longitude),
    height: text(height),
    vertical_distances: joinList(configuration.verticalDistance?.distances),
    vertical_unit: conceptCell(configuration.verticalDistance?.unit),
    reference_surface: conceptCell(configuration.verticalDistance?.referenceSurface),
  };
  Object.entries(CONCEPT_COLUMNS).forEach(([column, { field }]) => (cells[column] = conceptCell(configuration[field])));
  Object.entries(INSTRUMENT_COLUMNS).forEach(([column, field]) => (cells[column] = text(configuration.instrument?.[field])));
  return cells;
}

export function toRows(entries) {
  return entries.flatMap((entry) => {
    const station = stationKeys(entry);
    return observationsOf(entry.record).flatMap((observation, obsIndex) => {
      const keys = { ...station, observed_property: observedPropertyLabel(observation) };
      return (observation.configurations || []).map((configuration, itemIndex) =>
        makeRow(`${entry.stationId}:${obsIndex}:${itemIndex}`, entry.stationId, keys, configurationCells(configuration), {
          obsIndex,
          itemIndex,
          aliases: observationAliases(observation),
        })
      );
    });
  });
}

// Writes a group of cells into a nested object, dropping the object when it
// ends up empty.
function writeNested(parent, key, update) {
  const nested = { ...(parent[key] || {}) };
  update(nested);
  setOrDelete(parent, key, Object.keys(nested).length ? nested : null);
}

function writeConfiguration(configuration, cells, changed, codelists) {
  if (changed.has("interval_start") || changed.has("interval_end")) {
    // `time` is required but may be null; its other keys are kept.
    const time = { ...(configuration.time || {}) };
    setOrDelete(time, "interval", datesFromCells(cells.interval_start, cells.interval_end));
    configuration.time = Object.keys(time).length ? time : null;
  }

  Object.entries(CONCEPT_COLUMNS).forEach(([column, { field, codelist }]) => {
    if (!changed.has(column)) return;
    const options = codelistOptions(codelist, codelists);
    setOrDelete(configuration, field, conceptForCell(cells[column], options, configuration[field]));
  });

  if (Object.keys(INSTRUMENT_COLUMNS).some((column) => changed.has(column))) {
    writeNested(configuration, "instrument", (instrument) => {
      Object.entries(INSTRUMENT_COLUMNS).forEach(([column, field]) => {
        if (changed.has(column)) setOrDelete(instrument, field, cells[column]);
      });
    });
  }

  if (changed.has("instrument_serial_number")) {
    setOrDelete(configuration, "instrumentSerialNumber", cells.instrument_serial_number);
  }

  if (["latitude", "longitude", "height"].some((column) => changed.has(column))) {
    const { latitude, longitude, height } = cells;
    if (!latitude && !longitude && !height) {
      delete configuration.geometry;
    } else {
      const coordinates = [toNumber(longitude), toNumber(latitude)];
      if (height) coordinates.push(toNumber(height));
      configuration.geometry = { ...(configuration.geometry || {}), type: "Point", coordinates };
    }
  }

  if (["vertical_distances", "vertical_unit", "reference_surface"].some((column) => changed.has(column))) {
    writeNested(configuration, "verticalDistance", (verticalDistance) => {
      if (changed.has("vertical_distances")) {
        setOrDelete(verticalDistance, "distances", splitList(cells.vertical_distances).map(toNumber));
      }
      if (changed.has("vertical_unit")) {
        const options = codelistOptions("unit", codelists);
        setOrDelete(verticalDistance, "unit", conceptForCell(cells.vertical_unit, options, verticalDistance.unit));
      }
      if (changed.has("reference_surface")) {
        const options = codelistOptions("referenceSurface", codelists);
        setOrDelete(
          verticalDistance,
          "referenceSurface",
          conceptForCell(cells.reference_surface, options, verticalDistance.referenceSurface)
        );
      }
    });
  }
}

export function applyRows(entries, rows, codelists) {
  return applyRowsWith(entries, rows, columns, (record, row, changed) => {
    const configuration = observationsOf(record)[row.obsIndex]?.configurations?.[row.itemIndex];
    if (configuration) writeConfiguration(configuration, row.cells, changed, codelists);
  });
}
