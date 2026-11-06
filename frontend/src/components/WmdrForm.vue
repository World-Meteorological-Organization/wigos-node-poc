<script>
const initialState = () => ({
  id: "",
  latitude: "",
  longitude: "",
  height: "",
  time: { date: "", timestamp: "", intervalStart: "", intervalEnd: "", resolution: "" },
  title: "",
  description: "",
  additionalTitles: [""],
  additionalIds: [],
  facilityType: null,
  wmoRegion: null,
  contacts: [],
  // Not shown: buildWmdrRecord sets created (for a new record) and updated.
  created: "",
  territories: [],
  externalIds: [],
  observations: [],
  links: [],
});

const EXTERNAL_ID_FIELDS = [
  { name: "value", label: "Identifier", type: "text", required: true },
  { name: "scheme", label: "Scheme", type: "text", placeholder: "Issuing authority, ideally a resolvable URI" },
];

import { DATES_FIELD } from "../fieldDefs";

const territoryFields = (territoryNames) => [
  { name: "territory", label: "Territory", type: "concept", required: true, options: territoryNames },
  DATES_FIELD,
];

const externalIdSummary = (e) => [e.scheme, e.value].filter(Boolean).join(": ");
const territorySummary = (t) => t.territory?.id;
const linkSummary = (l) => l.title || l.href;
</script>

<script setup>
import { computed, ref } from "vue";
import { WIGOS_ID_PATTERN, buildWmdrRecord, parseWmdrRecord, duplicateWigosIds } from "../wmdr";
import { validateWmdrRecord } from "../wmdrSchema";
import { saveStation, getStation, getCodelist } from "../api";
import { useWigosIdAvailability } from "../composables/useWigosIdAvailability";
import { STATION_TIME_FIELDS, LINK_FIELDS } from "../fieldDefs";
import StringListField from "./StringListField.vue";
import WigosIdInput from "./WigosIdInput.vue";
import WigosIdFeedback from "./WigosIdFeedback.vue";
import WigosIdListField from "./WigosIdListField.vue";
import ContactsField from "./ContactsField.vue";
import ConceptField from "./ConceptField.vue";
import ObjectArrayField from "./ObjectArrayField.vue";
import ObjectArrayItemRow from "./ObjectArrayItemRow.vue";
import ObservationsField from "./ObservationsField.vue";
import MapPreview from "./MapPreview.vue";

// Creates a station, or edits the one with `stationId`. The parent re-mounts
// it (by key) for another station.
const props = defineProps({ stationId: { type: [String, Number], default: null } });
const emit = defineEmits(["saved", "cancel"]);

const isEditing = props.stationId != null;
const form = ref(initialState());
const submitState = ref({ status: "idle" });
const loadState = ref({ status: isEditing ? "loading" : "idle" });
const facilityTypes = ref([]);
const wmoRegions = ref([]);
const issuerCountries = ref([]);
const territoryNames = ref([]);
// IDs the station had when loaded for editing; they belong to it, so they aren't checked for availability.
const ownIds = ref([]);

getCodelist("FacilityType").then((options) => (facilityTypes.value = options)).catch(() => {});
getCodelist("WMORegion").then((options) => (wmoRegions.value = options)).catch(() => {});
getCodelist("ISO3166").then((options) => (issuerCountries.value = options)).catch(() => {});
getCodelist("TerritoryName")
  .then((options) => (territoryNames.value = [...options].sort((a, b) => a.label.localeCompare(b.label))))
  .catch(() => {});

if (isEditing) {
  getStation(props.stationId)
    .then((record) => {
      const parsed = parseWmdrRecord(record);
      form.value = parsed;
      ownIds.value = [parsed.id, ...parsed.additionalIds].filter(Boolean);
      loadState.value = { status: "success" };
    })
    .catch((err) => {
      loadState.value = { status: "error", error: err.message };
    });
}

const allIds = computed(() => [form.value.id, ...form.value.additionalIds]);
const duplicateIds = computed(() => duplicateWigosIds(allIds.value));
const idStatusOf = useWigosIdAvailability(allIds, ownIds);
// An unavailable or still-unchecked ID blocks saving; a failed check doesn't, as the backend re-checks on save.
const idsBlocked = computed(() =>
  allIds.value.some(
    (id) =>
      (id && !WIGOS_ID_PATTERN.test(id)) ||
      duplicateIds.value.has(id) ||
      ["taken", "checking"].includes(idStatusOf(id))
  )
);

const record = computed(() => buildWmdrRecord(form.value));
const schemaErrors = computed(() => validateWmdrRecord(record.value));
const schemaValid = computed(() => schemaErrors.value.length === 0);
const valid = computed(() => schemaValid.value && !idsBlocked.value);
const recordJson = computed(() => JSON.stringify(record.value, null, 2));

async function handleSubmit() {
  if (!valid.value) return;
  submitState.value = { status: "loading" };
  try {
    const data = await saveStation(props.stationId, record.value);
    submitState.value = { status: "success", data };
    emit("saved", data.station_id);
  } catch (err) {
    submitState.value = { status: "error", error: err.message };
  }
}

const submitLabel = computed(() => (isEditing ? "Save changes" : "Save WMDR record"));
</script>

<template>
  <v-btn
    class="back-button"
    color="primary"
    variant="flat"
    elevation="4"
    rounded="pill"
    prepend-icon="mdi-chevron-left"
    @click="emit('cancel')"
  >
    Back to stations
  </v-btn>
  <!-- Keeps the floating button from covering the top of the form before scrolling. -->
  <div class="back-button-spacer" />

  <v-card v-if="isEditing && loadState.status === 'loading'" class="pa-6">Loading station...</v-card>
  <v-alert v-else-if="isEditing && loadState.status === 'error'" type="error" variant="tonal">
    Error: {{ loadState.error }}
  </v-alert>

  <v-row v-else>
    <v-col cols="12" md="7">
      <v-form @submit.prevent="handleSubmit">
        <v-card class="pa-6 mb-5">
          <h3 class="section-title">Identification</h3>
          <div class="wigos-id-box">
            <div class="group-label">WIGOS station identifier<span class="required-mark">*</span></div>
            <WigosIdInput v-model="form.id" :issuer-countries="issuerCountries" :disabled="isEditing" />
            <WigosIdFeedback :id="form.id" :status="idStatusOf(form.id)" :duplicate="duplicateIds.has(form.id)" />

            <div class="mt-4">
              <WigosIdListField
                v-model="form.additionalIds"
                label="Additional WIGOS identifiers"
                :issuer-countries="issuerCountries"
                :status-of="idStatusOf"
                :duplicates="duplicateIds"
              />
            </div>
          </div>

          <v-row density="compact" class="mb-2">
            <v-col cols="12" sm="4">
              <v-text-field v-model="form.latitude" label="Latitude *" type="number" step="any" />
            </v-col>
            <v-col cols="12" sm="4">
              <v-text-field v-model="form.longitude" label="Longitude *" type="number" step="any" />
            </v-col>
            <v-col cols="12" sm="4">
              <v-text-field
                v-model="form.height"
                label="Height (m)"
                type="number"
                step="any"
                placeholder="Above sea level"
              />
            </v-col>
          </v-row>

          <div class="nested-card">
            <div class="nested-card-header"><span>Time</span></div>
            <ObjectArrayItemRow v-model:item="form.time" :fields="STATION_TIME_FIELDS" :path="['time']" />
          </div>
        </v-card>

        <v-card class="pa-6 mb-5">
          <h3 class="section-title">Properties</h3>
          <v-text-field v-model="form.title" class="mb-3" label="Title *" />
          <v-textarea v-model="form.description" class="mb-4" label="Description" rows="3" auto-grow />

          <StringListField v-model="form.additionalTitles" label="Additional titles" />
          <ObjectArrayField
            v-model="form.externalIds"
            label="External IDs"
            item-label="External ID"
            :fields="EXTERNAL_ID_FIELDS"
            :item-summary="externalIdSummary"
            :path="[]"
          />

          <v-row density="compact" class="mb-3">
            <v-col cols="12" sm="6">
              <ConceptField v-model="form.facilityType" label="Facility type" :options="facilityTypes" />
            </v-col>
            <v-col cols="12" sm="6">
              <ConceptField v-model="form.wmoRegion" label="WMO region" :options="wmoRegions" />
            </v-col>
          </v-row>

          <ContactsField v-model="form.contacts" />

          <ObjectArrayField
            v-model="form.territories"
            label="Territories"
            item-label="Territory"
            :fields="territoryFields(territoryNames)"
            :item-summary="territorySummary"
            :path="[]"
          />
          <ObservationsField v-model="form.observations" />
        </v-card>

        <v-card class="pa-6 mb-5">
          <h3 class="section-title">Links</h3>
          <ObjectArrayField
            v-model="form.links"
            label="Links"
            item-label="Link"
            :fields="LINK_FIELDS"
            :item-summary="linkSummary"
            :path="[]"
          />
          <p class="text-caption text-medium-emphasis">A link to this record on this node is added automatically.</p>
        </v-card>

        <div class="d-flex ga-3 align-center">
          <v-btn type="submit" color="primary" size="large" :disabled="!valid" :loading="submitState.status === 'loading'">
            {{ submitLabel }}
          </v-btn>
          <v-btn variant="outlined" size="large" @click="emit('cancel')">Cancel</v-btn>
        </div>

        <v-alert v-if="submitState.status === 'success'" class="mt-4" type="success" variant="tonal">
          Saved successfully.
        </v-alert>
        <v-alert v-if="submitState.status === 'error'" class="mt-4" type="error" variant="tonal">
          Error: {{ submitState.error }}
        </v-alert>
      </v-form>
    </v-col>

    <v-col cols="12" md="5">
      <div class="sticky-col">
        <v-card class="pa-6 mb-5">
          <h3 class="section-title">Map</h3>
          <MapPreview :latitude="form.latitude" :longitude="form.longitude" />
        </v-card>
        <v-card class="pa-6">
          <h3 class="section-title">GeoJSON preview</h3>
          <v-alert v-if="schemaValid" type="success" variant="tonal" density="compact">
            Valid against the WMDR2 schema.
          </v-alert>
          <v-alert v-else type="error" variant="tonal" density="compact">
            Not yet valid against the WMDR2 schema:
            <ul class="schema-errors">
              <li v-for="error in schemaErrors" :key="error">{{ error }}</li>
            </ul>
          </v-alert>
          <pre class="geojson-preview">{{ recordJson }}</pre>
        </v-card>
      </div>
    </v-col>
  </v-row>
</template>

<style scoped>
/* Stays in the top-left corner, below the 88px app bar, while the form scrolls. */
.back-button {
  position: fixed;
  top: 104px;
  left: 16px;
  z-index: 5;
}

.back-button-spacer {
  height: 52px;
}

/* Groups the primary and additional WIGOS identifiers. */
.wigos-id-box {
  margin-bottom: 1rem;
  padding: 1rem;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
}

.sticky-col {
  position: sticky;
  top: 104px; /* below the 88px app bar */
}

.schema-errors {
  margin: 0.4rem 0 0;
  padding-left: 1.2rem;
  max-height: 160px;
  overflow: auto;
  font-size: 0.85rem;
}

.geojson-preview {
  margin-top: 1rem;
  padding: 1rem;
  min-height: 180px;
  max-height: 420px;
  overflow: auto;
  border-radius: 8px;
  background: #0f172a;
  color: #e2e8f0;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 0.8rem;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
