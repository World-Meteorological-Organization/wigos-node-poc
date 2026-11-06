import { getCodelist } from "./api";

// Codelists (cached by the backend, see populate_codelists) behind each
// concept field: a scheme name for a single list, or labelled schemes for a
// field whose concepts come from several lists, shown as option groups.
export const CODELISTS = {
  observedProperty: [
    { scheme: "ObservedVariableAtmosphere", label: "Atmosphere" },
    { scheme: "ObservedVariableOcean", label: "Ocean" },
    { scheme: "ObservedVariableTerrestrial", label: "Terrestrial" },
    { scheme: "ObservedVariableOuterSpace", label: "Outer space" },
    { scheme: "ObservedVariableEarth", label: "Earth" },
  ],
  observedGeometry: "Geometry",
  programAffiliation: "ProgramAffiliation",
  reportingStatus: "ReportingStatus",
  observingMethod: [
    { scheme: "ObservingMethodAtmosphere", label: "Atmosphere" },
    { scheme: "ObservingMethodOcean", label: "Ocean" },
    { scheme: "ObservingMethodTerrestrial", label: "Terrestrial" },
  ],
  operatingStatus: "InstrumentOperatingStatus",
  sourceOfObservation: "SourceOfObservation",
  unit: "unit",
  referenceSurface: "ReferenceSurfaceType",
};

const sortByLabel = (options) => [...options].sort((a, b) => a.label.localeCompare(b.label));

export function loadCodelist(spec) {
  if (typeof spec === "string") return getCodelist(spec).then(sortByLabel).catch(() => []);
  return Promise.all(
    spec.map(({ scheme, label }) =>
      getCodelist(scheme)
        .then((options) => ({ label, options: sortByLabel(options) }))
        .catch(() => ({ label, options: [] }))
    )
  );
}

// `options` for a single list, `groups` for several.
export const codelistProps = (name, codelists) =>
  typeof CODELISTS[name] === "string" ? { options: codelists[name] } : { groups: codelists[name] };

// Every entry of a codelist, flattening option groups.
export const codelistOptions = (name, codelists) => {
  const list = codelists[name] || [];
  return typeof CODELISTS[name] === "string" ? list : list.flatMap((group) => group.options);
};
