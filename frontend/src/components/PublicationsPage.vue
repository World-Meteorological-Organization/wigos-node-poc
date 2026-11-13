<script setup>
import { computed, onUnmounted, ref, watch } from "vue";
import { listPublications, retryPublication } from "../api";
import PublicationStatusChip, { PUBLICATION_STATUSES } from "./PublicationStatusChip.vue";

const emit = defineEmits(["changed"]);

const PAGE_SIZE = 50;
const REFRESH_MS = 5000; // while a station is on its way

const FILTERS = [
  { title: "All", value: null },
  ...Object.entries(PUBLICATION_STATUSES).map(([value, { label }]) => ({ title: label, value })),
];

const rows = ref([]);
const total = ref(0);
const filter = ref(null);
const loadState = ref({ status: "loading" });
const retrying = ref(new Set());
const retryError = ref(null);

let timer = null;
let requests = 0;

const hasMore = computed(() => rows.value.length < total.value);
const isActive = (row) => row.status === "pending" || row.status === "processing";

// Fetches the first `limit` stations. A slower, older answer is dropped, and a
// failing refresh keeps what is shown.
async function load(limit) {
  const request = ++requests;
  clearTimeout(timer);
  try {
    const data = await listPublications({ status: filter.value, limit, offset: 0 });
    if (request !== requests) return;
    rows.value = data.results;
    total.value = data.count;
    loadState.value = { status: "success" };
    emit("changed");
  } catch (err) {
    if (request !== requests) return;
    loadState.value = { status: "error", error: err.message };
  }
  if (rows.value.some(isActive)) {
    timer = setTimeout(() => load(Math.max(rows.value.length, PAGE_SIZE)), REFRESH_MS);
  }
}

const refresh = () => load(Math.max(rows.value.length, PAGE_SIZE));
const loadMore = () => load(rows.value.length + PAGE_SIZE);

async function retry(row) {
  retryError.value = null;
  retrying.value = new Set(retrying.value).add(row.station_id);
  try {
    await retryPublication(row.station_id);
  } catch (err) {
    retryError.value = `${row.wigos_identifier}: ${err.message}`;
  }
  const remaining = new Set(retrying.value);
  remaining.delete(row.station_id);
  retrying.value = remaining;
  await refresh();
}

watch(filter, () => {
  loadState.value = { status: "loading" };
  rows.value = [];
  load(PAGE_SIZE);
}, { immediate: true });

onUnmounted(() => {
  requests += 1; // drops an answer still on its way, which would start the timer again
  clearTimeout(timer);
});

const formatTime = (value) => (value ? new Date(value).toLocaleString() : "");
</script>

<template>
  <v-card class="pa-6">
    <div class="list-header">
      <h3>Publishing</h3>
      <div class="list-actions">
        <v-select
          v-model="filter"
          :items="FILTERS"
          label="Show"
          density="compact"
          hide-details
          class="status-filter"
        />
        <v-btn variant="tonal" prepend-icon="mdi-refresh" @click="refresh">Refresh</v-btn>
      </div>
    </div>

    <p v-if="loadState.status === 'loading'">Loading…</p>
    <v-alert v-if="loadState.status === 'error'" type="error" variant="tonal" class="mb-3">
      Error: {{ loadState.error }}
    </v-alert>
    <v-alert
      v-if="retryError"
      type="error"
      variant="tonal"
      class="mb-3"
      closable
      @click:close="retryError = null"
    >
      {{ retryError }}
    </v-alert>
    <p v-if="loadState.status === 'success' && rows.length === 0" class="empty">
      {{ filter ? "No stations with this status." : "None of your stations have been published yet." }}
    </p>

    <template v-if="rows.length > 0">
      <v-table class="publications">
        <thead>
          <tr>
            <th>Last updated</th>
            <th>WIGOS identifier</th>
            <th>By</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.station_id">
            <td class="when">{{ formatTime(row.updated) }}</td>
            <td>{{ row.wigos_identifier }}</td>
            <td>{{ row.changed_by || "Administrator" }}</td>
            <td><PublicationStatusChip :status="row.status" /></td>
            <td class="row-actions">
              <v-btn
                v-if="row.can_retry"
                color="primary"
                size="small"
                :loading="retrying.has(row.station_id)"
                @click="retry(row)"
              >
                Retry
              </v-btn>
            </td>
          </tr>
        </tbody>
      </v-table>
      <div v-if="hasMore" class="more">
        <v-btn variant="tonal" @click="loadMore">Show more</v-btn>
      </div>
    </template>
  </v-card>
</template>

<style scoped>
.list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.75rem;
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

.list-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.status-filter {
  width: 13rem;
  flex: none;
}

.publications td {
  padding-top: 0.5rem !important;
  padding-bottom: 0.5rem !important;
  vertical-align: top;
}

.when {
  white-space: nowrap;
}

.row-actions {
  text-align: end;
}

.more {
  display: flex;
  justify-content: center;
  margin-top: 1rem;
}
</style>
