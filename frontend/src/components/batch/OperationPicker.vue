<script setup>
import { OPERATIONS } from "../../batch/operations";

defineProps({ stationCount: { type: Number, required: true } });
const emit = defineEmits(["pick"]);
</script>

<template>
  <div>
    <p class="batch-intro">
      Choose what to change in the {{ stationCount }} selected {{ stationCount === 1 ? "station" : "stations" }}. The
      next step shows their current values in a spreadsheet you can edit, or export to Excel and import back.
    </p>
    <div class="operation-cards">
      <v-card
        v-for="operation in OPERATIONS"
        :key="operation.id"
        class="operation-card"
        variant="outlined"
        @click="emit('pick', operation)"
      >
        <v-card-title class="operation-card-name">{{ operation.name }}</v-card-title>
        <v-card-text>
          <p class="operation-card-description">{{ operation.description }}</p>
          <p class="operation-card-rows">{{ operation.rowLabel }}</p>
        </v-card-text>
      </v-card>
    </div>
  </div>
</template>

<style scoped>
.batch-intro {
  margin: 0 0 1rem;
  color: #475569;
  font-size: 0.9rem;
}

.operation-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 1rem;
}

.operation-card {
  border-color: #e2e8f0;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.operation-card:hover,
.operation-card:focus-visible {
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px #dbeafe;
}

.operation-card-name {
  font-size: 1rem;
  font-weight: 700;
  color: #1e3a8a;
  white-space: normal;
}

.operation-card-description {
  margin: 0 0 0.5rem;
  font-size: 0.85rem;
  color: #475569;
}

.operation-card-rows {
  margin: 0;
  font-size: 0.75rem;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
</style>
