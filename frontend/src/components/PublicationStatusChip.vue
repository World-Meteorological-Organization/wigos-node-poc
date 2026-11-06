<script>
export const PUBLICATION_STATUSES = {
  pending: { label: "Pending", color: "info", icon: "mdi-clock-outline" },
  processing: { label: "Publishing", color: "info", icon: "mdi-progress-upload" },
  processed: { label: "Processed", color: "success", icon: "mdi-check" },
  published: { label: "Published", color: "success", icon: "mdi-check-all" },
  failed: { label: "Publishing failed", color: "error", icon: "mdi-close" },
};

// A station with no status in the database. Not a status to filter by.
const UNKNOWN = { label: "Unknown", color: "grey", icon: "mdi-help" };
</script>

<script setup>
import { computed } from "vue";

const props = defineProps({ status: { type: String, required: true } });
const shown = computed(() => PUBLICATION_STATUSES[props.status] ?? UNKNOWN);
</script>

<template>
  <v-chip size="small" variant="tonal" :color="shown.color" :prepend-icon="shown.icon">
    {{ shown.label }}
  </v-chip>
</template>
