<script setup>
// A list of strings that always keeps at least one (possibly empty) entry.
defineProps({
  label: { type: String, required: true },
  placeholder: String,
  required: Boolean,
});
const values = defineModel({ type: Array, required: true });

const update = (index, value) => {
  values.value = values.value.map((v, i) => (i === index ? value : v));
};
const add = () => {
  values.value = [...values.value, ""];
};
const remove = (index) => {
  const next = values.value.filter((_, i) => i !== index);
  values.value = next.length ? next : [""];
};
</script>

<template>
  <div class="mb-4">
    <div class="group-label">
      {{ label }}<span v-if="required" class="required-mark">*</span>
    </div>
    <div v-for="(value, i) in values" :key="i" class="input-row mb-2">
      <v-text-field
        :model-value="value"
        :placeholder="placeholder"
        :aria-label="`${label} ${i + 1}`"
        @update:model-value="(next) => update(i, next)"
      />
      <v-btn variant="outlined" :disabled="values.length <= 1" @click="remove(i)">Remove</v-btn>
    </div>
    <v-btn variant="tonal" color="secondary" size="small" prepend-icon="mdi-plus" @click="add">Add</v-btn>
  </div>
</template>
