<script setup>
import { computed } from "vue";

// Lists the changes per station with the frontend schema check and the
// backend dry run. `changes`: [{ stationId, name, wsi, diff, schemaErrors }];
// `dryRun`: { status: "running" | "done" | "error", byStation, error }.
const props = defineProps({
  changes: { type: Array, required: true },
  unchangedCount: { type: Number, required: true },
  dryRun: { type: Object, required: true },
});
const emit = defineEmits(["confirm", "back"]);

const show = (value) => (value === undefined ? "—" : JSON.stringify(value));
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

const schemaFailures = computed(() => props.changes.filter((change) => change.schemaErrors.length).length);
const dryRunFailures = computed(() =>
  props.dryRun.status === "done"
    ? props.changes.filter((change) => props.dryRun.byStation[change.stationId]?.status !== "ok").length
    : 0
);
const canConfirm = computed(
  () => props.changes.length > 0 && !schemaFailures.value && props.dryRun.status === "done" && !dryRunFailures.value
);
const failureSummary = computed(() =>
  [
    schemaFailures.value && `${schemaFailures.value} failing the schema check`,
    dryRunFailures.value && `${dryRunFailures.value} rejected by the server`,
  ]
    .filter(Boolean)
    .join(", ")
);
</script>

<template>
  <v-dialog :model-value="true" max-width="960" scrollable @update:model-value="(open) => !open && emit('back')">
    <v-card>
      <v-card-title class="d-flex align-center">
        <span>Review changes</span>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="emit('back')" />
      </v-card-title>
      <v-divider />
      <v-card-text>
        <p class="batch-intro">
          {{ plural(changes.length, "station", "stations") }} will be changed<template v-if="unchangedCount > 0"
            >, {{ plural(unchangedCount, "unchanged station is", "unchanged stations are") }} not sent</template
          >.
        </p>

        <v-alert v-if="dryRun.status === 'running'" class="mb-3" type="info" variant="tonal" density="compact">
          Checking the changes on the server…
        </v-alert>
        <v-alert v-if="dryRun.status === 'error'" class="mb-3" type="error" variant="tonal" density="compact">
          The server check failed: {{ dryRun.error }}
        </v-alert>
        <v-alert v-if="failureSummary" class="mb-3" type="error" variant="tonal" density="compact">
          Fix the stations marked below before confirming ({{ failureSummary }}).
        </v-alert>

        <div class="preview-list">
          <div v-for="change in changes" :key="change.stationId" class="preview-station">
            <div class="preview-station-header">
              <span>
                <strong>{{ change.name || `Station ${change.stationId}` }}</strong>
                <span class="preview-wsi">{{ change.wsi }}</span>
              </span>
              <span class="preview-badges">
                <v-chip
                  size="small"
                  variant="tonal"
                  :color="change.schemaErrors.length ? 'error' : 'success'"
                  :prepend-icon="change.schemaErrors.length ? 'mdi-close' : 'mdi-check'"
                >
                  schema
                </v-chip>
                <v-chip v-if="dryRun.status === 'running'" size="small" variant="tonal">server…</v-chip>
                <v-chip
                  v-if="dryRun.byStation?.[change.stationId]"
                  size="small"
                  variant="tonal"
                  :color="dryRun.byStation[change.stationId].status === 'ok' ? 'success' : 'error'"
                  :prepend-icon="dryRun.byStation[change.stationId].status === 'ok' ? 'mdi-check' : 'mdi-close'"
                >
                  server
                </v-chip>
              </span>
            </div>
            <table class="preview-diff">
              <tbody>
                <tr v-for="entry in change.diff" :key="entry.path">
                  <td class="preview-path">{{ entry.path }}</td>
                  <td class="preview-before">{{ show(entry.before) }}</td>
                  <td class="preview-arrow">→</td>
                  <td class="preview-after">{{ show(entry.after) }}</td>
                </tr>
              </tbody>
            </table>
            <ul v-if="change.schemaErrors.length > 0" class="error-list text-error">
              <li v-for="error in change.schemaErrors" :key="error">{{ error }}</li>
            </ul>
            <div
              v-if="dryRun.byStation?.[change.stationId] && dryRun.byStation[change.stationId].status !== 'ok'"
              class="text-error mt-2"
            >
              {{ dryRun.byStation[change.stationId].message }}
              <ul v-if="dryRun.byStation[change.stationId].errors?.length > 0" class="error-list">
                <li v-for="error in dryRun.byStation[change.stationId].errors" :key="error">{{ error }}</li>
              </ul>
            </div>
          </div>
        </div>
      </v-card-text>
      <v-divider />
      <v-card-actions class="justify-end">
        <v-btn variant="outlined" @click="emit('back')">Back to editing</v-btn>
        <v-btn color="primary" variant="flat" :disabled="!canConfirm" @click="emit('confirm')">
          Confirm and save {{ plural(changes.length, "station", "stations") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.batch-intro {
  margin: 0 0 1rem;
  color: #475569;
  font-size: 0.9rem;
}

.preview-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.preview-station {
  padding: 0.75rem;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
}

.preview-station-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
  font-size: 0.9rem;
}

.preview-wsi {
  margin-left: 0.4rem;
  color: #64748b;
  font-size: 0.85rem;
}

.preview-badges {
  display: flex;
  gap: 0.35rem;
  flex-shrink: 0;
}

.preview-diff {
  width: 100%;
  border-collapse: collapse;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 0.75rem;
}

.preview-diff td {
  padding: 0.2rem 0.4rem;
  vertical-align: top;
  word-break: break-word;
  border-top: 1px solid #e2e8f0;
}

.preview-path {
  width: 35%;
  color: #475569;
}

.preview-before {
  color: #dc2626;
  text-decoration: line-through;
}

.preview-arrow {
  width: 1rem;
  color: #64748b;
}

.preview-after {
  color: #059669;
}

.error-list {
  margin: 0.4rem 0 0;
  padding-left: 1.2rem;
  font-size: 0.85rem;
}
</style>
