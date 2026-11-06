<script setup>
import { computed } from "vue";
import { resultsToCsv } from "../../batch/common";
import { csvBlob, downloadBlob } from "../../batch/sheetIO";

// `state`: { status: "running", count } | { status: "done", response } | { status: "error", error }.
const props = defineProps({ state: { type: Object, required: true } });
const emit = defineEmits(["retry", "retry-failed", "back"]);

const failed = computed(() =>
  props.state.status === "done" ? props.state.response.results.filter((result) => result.status !== "ok") : []
);

const download = () => downloadBlob(csvBlob(resultsToCsv(props.state.response.results)), "batch-results.csv");
</script>

<template>
  <v-alert v-if="state.status === 'running'" type="info" variant="tonal">
    Applying changes to {{ state.count }} {{ state.count === 1 ? "station" : "stations" }}…
  </v-alert>

  <div v-else-if="state.status === 'error'">
    <v-alert type="error" variant="tonal">The changes could not be sent: {{ state.error }}</v-alert>
    <div class="batch-actions">
      <v-btn variant="outlined" @click="emit('back')">Back to stations</v-btn>
      <v-btn color="primary" @click="emit('retry')">Retry</v-btn>
    </div>
  </div>

  <div v-else>
    <v-alert :type="failed.length ? 'error' : 'success'" variant="tonal" class="mb-3">
      {{ state.response.summary.ok }} saved, {{ state.response.summary.error }} failed.
    </v-alert>
    <v-table class="batch-results">
      <thead>
        <tr>
          <th>Station</th>
          <th>WIGOS ID</th>
          <th>Result</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="result in state.response.results" :key="result.index">
          <td>{{ result.station_name || `Station ${result.station_id}` }}</td>
          <td>{{ result.wsi }}</td>
          <td>
            <v-chip v-if="result.status === 'ok'" size="small" variant="tonal" color="success" prepend-icon="mdi-check">
              saved
            </v-chip>
            <template v-else>
              <v-chip size="small" variant="tonal" color="error" prepend-icon="mdi-close">failed</v-chip>
              {{ result.message }}
              <ul v-if="result.errors?.length > 0" class="error-list text-error">
                <li v-for="error in result.errors" :key="error">{{ error }}</li>
              </ul>
            </template>
          </td>
        </tr>
      </tbody>
    </v-table>
    <div class="batch-actions">
      <v-btn variant="outlined" @click="emit('back')">Back to stations</v-btn>
      <v-btn variant="tonal" color="secondary" prepend-icon="mdi-download" @click="download">Download results (CSV)</v-btn>
      <v-btn v-if="failed.length > 0" color="primary" @click="emit('retry-failed', failed.map((result) => result.station_id))">
        Retry {{ failed.length }} failed
      </v-btn>
    </div>
  </div>
</template>

<style scoped>
.batch-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 1rem;
}

.batch-results td {
  padding-top: 0.4rem !important;
  padding-bottom: 0.4rem !important;
  vertical-align: top;
}

.error-list {
  margin: 0.4rem 0 0;
  padding-left: 1.2rem;
  font-size: 0.85rem;
}
</style>
