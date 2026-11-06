<script>
import { codelistProps } from "../codelists";
import { TIME_FIELDS, GEOMETRY_FIELDS, DATES_FIELD } from "../fieldDefs";
import { describeInterval } from "../interval";

// Field names/shapes follow definitions/Observation, Configuration and
// Instrument in wmo-im/wmdr2 schemas/wmdr2-bundled.json. An observation's
// contacts have no field here: they are kept as stored (see wmdr.js).

const INSTRUMENT_FIELDS = [
  { name: "id", label: "Instrument ID", type: "text" },
  { name: "manufacturer", label: "Manufacturer", type: "text" },
  { name: "model", label: "Model", type: "text" },
];

function observationFields(codelists) {
  const concept = (name, label, extra) => ({ name, label, type: "concept", ...codelistProps(name, codelists), ...extra });

  const verticalDistanceFields = [
    { name: "distances", label: "Distances", type: "array-string", placeholder: "Signed distance from reference surface" },
    concept("unit", "Unit"),
    concept("referenceSurface", "Reference surface"),
  ];

  // No id field: buildWmdrRecord assigns one to a configuration without it.
  const configurationFields = [
    { name: "time", label: "Time", type: "object", fields: TIME_FIELDS },
    concept("observingMethod", "Observing method"),
    concept("operatingStatus", "Operating status"),
    concept("sourceOfObservation", "Source of observation"),
    { name: "geometry", label: "Location", type: "object", fields: GEOMETRY_FIELDS },
    { name: "instrument", label: "Instrument", type: "object", fields: INSTRUMENT_FIELDS },
    { name: "instrumentSerialNumber", label: "Instrument serial number", type: "text" },
    { name: "verticalDistance", label: "Vertical distance", type: "object", fields: verticalDistanceFields },
  ];

  const programAffiliationFields = [
    concept("programAffiliation", "Programme/network", { required: true }),
    concept("reportingStatus", "Reporting status"),
    DATES_FIELD,
  ];

  return [
    concept("observedProperty", "Observed property", { required: true }),
    concept("observedGeometry", "Observed geometry"),
    {
      name: "programAffiliations",
      label: "Program affiliation",
      type: "array-object",
      fields: programAffiliationFields,
      required: true,
      summary: (p) => p.programAffiliation?.title || p.programAffiliation?.id,
    },
    {
      name: "configurations",
      label: "Configuration",
      type: "array-object",
      fields: configurationFields,
      required: true,
      summary: configurationSummary,
    },
  ];
}

const observationSummary = (o) => o.observedProperty?.title || o.observedProperty?.id;

// e.g. "Vaisala HMP155 · Since 2020, ongoing · Operational". A configuration
// with none of these (a stored one may hold only its id) says so, rather than
// showing a blank card.
const configurationSummary = (c) =>
  [
    [c.instrument?.manufacturer, c.instrument?.model].filter(Boolean).join(" "),
    describeInterval(c.time?.intervalStart, c.time?.intervalEnd),
    c.operatingStatus?.title || c.operatingStatus?.id,
  ]
    .filter(Boolean)
    .join(" · ") || "No details yet";
</script>

<script setup>
import { computed } from "vue";
import DrillInArrayField from "./DrillInArrayField.vue";
import { useCodelists } from "../composables/useCodelists";

const observations = defineModel({ type: Array, required: true });
const { codelists } = useCodelists();
const fields = computed(() => observationFields(codelists.value));
</script>

<template>
  <DrillInArrayField
    v-model="observations"
    label="Observations"
    item-label="Observation"
    :fields="fields"
    :item-summary="observationSummary"
    required
  />
</template>
