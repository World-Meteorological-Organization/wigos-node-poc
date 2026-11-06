<script setup>
import { computed, onUnmounted, ref } from "vue";
import { listMyStations } from "../api";
import PublicationStatusChip from "./PublicationStatusChip.vue";
import StationsMap from "./StationsMap.vue";
import SelectionBar from "./SelectionBar.vue";

// `selected` (a Set of station IDs) is kept by the parent so it survives a
// trip to the batch wizard and back.
const selected = defineModel("selected", { type: Set, required: true });
const emit = defineEmits(["new", "edit", "batch", "changed"]);

const HEADERS = [
  { title: "WIGOS identifier", key: "wsi" },
  { title: "Name", key: "name" },
  { title: "Publishing", key: "publishing", sortable: false },
  { title: "", key: "actions", sortable: false, align: "end" },
];

const stations = ref([]);
const loadState = ref({ status: "loading" });

// Each station's publishing status, refreshed while one is on its way. Empty, as
// never queued, shows as unknown; null, as the user can't edit it, shows no chip.
// A refresh only updates these: new stations would make the map fit itself again.
const REFRESH_MS = 5000;
const statuses = ref({});
let timer = null;
let left = false;

async function load() {
  const firstLoad = loadState.value.status === "loading";
  try {
    const data = await listMyStations();
    if (left) return;
    if (firstLoad) {
      stations.value = data;
      loadState.value = { status: "success" };
    }
    statuses.value = Object.fromEntries(data.map((station) => [station.station_id, station.publication_status]));
    emit("changed");
  } catch (err) {
    if (firstLoad && !left) loadState.value = { status: "error", error: err.message };
    return; // a failing refresh keeps what is shown
  }
  if (Object.values(statuses.value).some((status) => status === "pending" || status === "processing")) {
    timer = setTimeout(load, REFRESH_MS);
  }
}
load();

onUnmounted(() => {
  left = true;
  clearTimeout(timer);
});

const editableIds = computed(() => stations.value.filter((station) => station.can_edit).map((station) => station.station_id));
// Only stations still listed and editable count as selected.
const selectedIds = computed(() => editableIds.value.filter((id) => selected.value.has(id)));

const setSelected = (ids) => {
  selected.value = new Set(ids);
};
const rowProps = ({ item }) => ({ class: selectedIds.value.includes(item.station_id) ? "row-selected" : "" });
</script>

<template>
  <v-card class="pa-6">
    <div class="list-header">
      <h3>My stations</h3>
      <v-btn color="primary" prepend-icon="mdi-plus" @click="emit('new')">New station</v-btn>
    </div>

    <p v-if="loadState.status === 'loading'">Loading stations...</p>
    <v-alert v-if="loadState.status === 'error'" type="error" variant="tonal">Error: {{ loadState.error }}</v-alert>
    <p v-if="loadState.status === 'success' && stations.length === 0">No stations saved yet.</p>

    <template v-if="stations.length > 0">
      <StationsMap :stations="stations" />
      <SelectionBar
        v-if="selectedIds.length > 0"
        :count="selectedIds.length"
        :editable-count="editableIds.length"
        @select-all="setSelected(editableIds)"
        @clear="setSelected([])"
        @batch="emit('batch', selectedIds)"
      />
      <v-data-table
        :headers="HEADERS"
        :items="stations"
        item-value="station_id"
        item-selectable="can_edit"
        show-select
        select-strategy="all"
        :model-value="selectedIds"
        :items-per-page="-1"
        hide-default-footer
        :row-props="rowProps"
        @update:model-value="setSelected"
      >
        <template #[`item.data-table-select`]="{ item, internalItem, isSelected, toggleSelect }">
          <v-checkbox-btn
            :model-value="isSelected(internalItem)"
            :disabled="!item.can_edit"
            :aria-label="`Select ${item.name || item.wsi}`"
            :title="item.can_edit ? undefined : `You don't have permission to edit this station`"
            @update:model-value="toggleSelect(internalItem)"
          />
        </template>
        <template #[`item.publishing`]="{ item }">
          <PublicationStatusChip v-if="statuses[item.station_id] != null" :status="statuses[item.station_id]" />
        </template>
        <template #[`item.actions`]="{ item }">
          <v-btn variant="tonal" color="secondary" size="small" @click="emit('edit', item.station_id)">Edit</v-btn>
        </template>
      </v-data-table>
    </template>
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

:deep(.row-selected) td {
  background: #eff6ff;
}
</style>
