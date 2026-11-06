<script setup>
import { computed, ref, shallowRef } from "vue";
import { getStations, saveStationsBatch } from "../../api";
import { useCodelists } from "../../composables/useCodelists";
import { useWigosIdStatus } from "../../composables/useWigosIdStatus";
import { blockingCellCount, changedColumns, diffRecord } from "../../batch/common";
import { validateWmdrRecord } from "../../wmdrSchema";
import { withNodeFields } from "../../wmdr";
import OperationPicker from "./OperationPicker.vue";
import SheetGrid from "./SheetGrid.vue";
import PreviewDialog from "./PreviewDialog.vue";
import BatchResults from "./BatchResults.vue";

const STEPS = [
  { id: "operation", label: "Operation" },
  { id: "edit", label: "Edit" },
  { id: "results", label: "Results" },
];

const props = defineProps({ stationIds: { type: Array, required: true } });
// `applied` carries the IDs of the stations that failed.
const emit = defineEmits(["applied", "close"]);

const { codelists } = useCodelists();
const step = ref("operation");
const stepIndex = computed(() => STEPS.findIndex((s) => s.id === step.value));
// Shallow: rows and previews are replaced, never mutated, and the dry-run
// reply is matched to its preview by identity, which a deep proxy would break.
const operation = shallowRef(null);
const load = shallowRef({ status: "idle" });
const entries = shallowRef([]);
const rows = shallowRef([]);
const selectedRows = shallowRef(new Set());
const preview = shallowRef(null);
const results = shallowRef(null);

const sheet = computed(() => operation.value?.module);
const cellStatus = useWigosIdStatus(() => operation.value?.id === "wigosIds", rows);

async function start(nextOperation, ids) {
  operation.value = nextOperation;
  step.value = "edit";
  load.value = { status: "loading" };
  preview.value = null;
  selectedRows.value = new Set();
  try {
    const records = await getStations(ids);
    const loaded = ids.filter((id) => records[id]).map((id) => ({ stationId: id, record: records[id] }));
    entries.value = loaded;
    rows.value = nextOperation.module.toRows(loaded);
    load.value = { status: "done", missing: ids.filter((id) => !records[id]) };
  } catch (err) {
    load.value = { status: "error", error: err.message, ids };
  }
}

const changedRows = computed(() => rows.value.filter((row) => changedColumns(row, sheet.value?.columns || []).length));
const changedCells = computed(() =>
  changedRows.value.reduce((sum, row) => sum + changedColumns(row, sheet.value.columns).length, 0)
);
const changedStations = computed(() => new Set(changedRows.value.map((row) => row.stationId)).size);
const invalidCells = computed(() =>
  sheet.value ? blockingCellCount(sheet.value.columns, rows.value, codelists.value, cellStatus) : 0
);
const applyBlockedReason = computed(() =>
  !changedCells.value
    ? "Edit at least one cell first"
    : invalidCells.value
      ? "Fix the cells outlined in red first (hover a cell to see why)"
      : undefined
);
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

async function openPreview() {
  const updated = sheet.value.applyRows(entries.value, rows.value, codelists.value);
  const changes = [];
  const now = new Date();
  updated.forEach((entry, i) => {
    const before = entries.value[i].record;
    // The diff shows the user's edits; `updated` and the self link are then set
    // on changed records only, so untouched stations stay out of the batch.
    const diff = diffRecord(before, entry.record);
    if (!diff.length) return;
    const record = withNodeFields(entry.record, { now });
    changes.push({
      stationId: entry.stationId,
      name: before.properties?.title,
      wsi: before.id,
      record,
      diff,
      schemaErrors: validateWmdrRecord(record),
    });
  });
  const unchangedCount = entries.value.length - changes.length;
  const updates = changes.map((change) => ({ station_id: change.stationId, wmdrv2: change.record }));
  preview.value = { changes, unchangedCount, updates, dryRun: { status: changes.length ? "running" : "done", byStation: {} } };
  if (!changes.length) return;

  let dryRun;
  try {
    const response = await saveStationsBatch(updates, { dryRun: true });
    dryRun = { status: "done", byStation: Object.fromEntries(response.results.map((r) => [r.station_id, r])) };
  } catch (err) {
    dryRun = { status: "error", error: err.message, byStation: {} };
  }
  // Ignore a reply for a preview that was closed in the meantime.
  if (preview.value?.updates === updates) preview.value = { ...preview.value, dryRun };
}

async function apply(updates, names) {
  preview.value = null;
  step.value = "results";
  results.value = { status: "running", count: updates.length, updates, names };
  try {
    const response = await saveStationsBatch(updates);
    response.results.forEach((result) => (result.station_name = names[result.station_id]));
    results.value = { status: "done", response, updates, names };
    emit(
      "applied",
      response.results.filter((r) => r.status !== "ok").map((r) => r.station_id)
    );
  } catch (err) {
    results.value = { status: "error", error: err.message, updates, names };
  }
}

function confirm() {
  const names = Object.fromEntries(preview.value.changes.map((change) => [change.stationId, change.name]));
  apply(preview.value.updates, names);
}

function addRows() {
  const { rows: next, added } = sheet.value.addRows(rows.value, selectedRows.value);
  rows.value = next;
  selectedRows.value = new Set(added.map((row) => row.id));
}
</script>

<template>
  <v-card class="pa-6">
    <div class="list-header">
      <h3>Batch operations{{ operation && step !== "operation" ? `: ${operation.name}` : "" }}</h3>
      <v-btn variant="text" color="secondary" prepend-icon="mdi-chevron-left" @click="emit('close')">
        Back to stations
      </v-btn>
    </div>

    <v-stepper :model-value="stepIndex" class="step-bar" flat>
      <v-stepper-header>
        <template v-for="(s, i) in STEPS" :key="s.id">
          <v-divider v-if="i > 0" />
          <v-stepper-item :value="i" :title="s.label" :complete="i < stepIndex" color="primary" />
        </template>
      </v-stepper-header>
    </v-stepper>

    <OperationPicker v-if="step === 'operation'" :station-count="stationIds.length" @pick="(op) => start(op, stationIds)" />

    <template v-if="step === 'edit'">
      <p v-if="load.status === 'loading'">Loading the selected stations…</p>
      <v-alert v-if="load.status === 'error'" type="error" variant="tonal">
        Couldn't load the stations: {{ load.error }}
        <template #append>
          <v-btn variant="outlined" @click="start(operation, load.ids)">Retry</v-btn>
        </template>
      </v-alert>
      <template v-if="load.status === 'done'">
        <v-alert v-if="load.missing.length > 0" class="mb-3" type="warning" variant="tonal" density="compact">
          {{ load.missing.length }} selected
          {{ load.missing.length === 1 ? "station no longer exists and is" : "stations no longer exist and are" }} left out.
        </v-alert>
        <SheetGrid
          :key="operation.id"
          v-model:rows="rows"
          v-model:selected-ids="selectedRows"
          :sheet="sheet"
          :codelists="codelists"
          :cell-status="cellStatus"
          :export-name="`batch-${operation.id}`"
        >
          <template v-if="sheet.addRows" #actions>
            <v-btn
              variant="tonal"
              color="secondary"
              prepend-icon="mdi-plus"
              :disabled="!selectedRows.size"
              title="Adds an empty affiliation under the observation of each selected row"
              @click="addRows"
            >
              Add affiliation to selected observations
            </v-btn>
          </template>
        </SheetGrid>
        <div class="batch-footer">
          <span class="batch-count">
            {{
              changedCells
                ? `${plural(changedCells, "cell", "cells")} changed in ${plural(changedStations, "station", "stations")}`
                : "No changes yet"
            }}
            <span v-if="invalidCells > 0" class="text-error">
              · {{ invalidCells }} edited {{ invalidCells === 1 ? "cell is" : "cells are" }} invalid (outlined in red,
              hover for the reason)
            </span>
          </span>
          <div class="d-flex ga-3">
            <v-btn variant="outlined" @click="step = 'operation'">Change operation</v-btn>
            <v-btn variant="text" @click="emit('close')">Cancel</v-btn>
            <!-- The wrapper shows the reason: a disabled button gets no hover. -->
            <span :title="applyBlockedReason">
              <v-btn color="primary" :disabled="!!applyBlockedReason" @click="openPreview">Apply</v-btn>
            </span>
          </div>
        </div>
      </template>
    </template>

    <BatchResults
      v-if="step === 'results' && results"
      :state="results"
      @retry="apply(results.updates, results.names)"
      @retry-failed="(ids) => start(operation, ids)"
      @back="emit('close')"
    />

    <PreviewDialog
      v-if="preview"
      :changes="preview.changes"
      :unchanged-count="preview.unchangedCount"
      :dry-run="preview.dryRun"
      @confirm="confirm"
      @back="preview = null"
    />
  </v-card>
</template>

<style scoped>
.list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
  border-bottom: 1px solid #dbeafe;
  padding-bottom: 0.5rem;
}

.list-header h3 {
  margin: 0;
  font-size: 1rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #2563eb;
}

.step-bar {
  margin-bottom: 1.25rem;
  background: transparent;
}

.step-bar :deep(.v-stepper-header) {
  box-shadow: none;
}

.batch-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 1rem;
}

.batch-count {
  font-size: 0.9rem;
  color: #475569;
}
</style>
