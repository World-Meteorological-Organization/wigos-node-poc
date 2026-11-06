<script setup>
import WigosIdInput from "./WigosIdInput.vue";
import WigosIdFeedback from "./WigosIdFeedback.vue";

// A list of WIGOS IDs, each entered part by part like the primary identifier.
// Starts empty: rows only appear once "Add" is pressed, and every row can be removed.
defineProps({
  label: { type: String, required: true },
  issuerCountries: { type: Array, required: true },
  statusOf: { type: Function, required: true },
  duplicates: { type: Set, required: true },
});
const values = defineModel({ type: Array, required: true });

const update = (index, value) => {
  values.value = values.value.map((v, i) => (i === index ? value : v));
};
const add = () => {
  values.value = [...values.value, ""];
};
const remove = (index) => {
  values.value = values.value.filter((_, i) => i !== index);
};
</script>

<template>
  <div>
    <div v-if="values.length > 0" class="group-label">{{ label }}</div>
    <div v-for="(value, i) in values" :key="i" class="mb-3">
      <div class="input-row">
        <WigosIdInput
          :model-value="value"
          :issuer-countries="issuerCountries"
          :label-prefix="`${label} ${i + 1}: `"
          @update:model-value="(next) => update(i, next)"
        />
        <v-btn variant="outlined" @click="remove(i)">Remove</v-btn>
      </div>
      <WigosIdFeedback :id="value" :status="statusOf(value)" :duplicate="duplicates.has(value)" />
    </div>
    <v-btn variant="tonal" color="secondary" size="small" prepend-icon="mdi-plus" @click="add">
      Add additional WIGOS identifier
    </v-btn>
  </div>
</template>
