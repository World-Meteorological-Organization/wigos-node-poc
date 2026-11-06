<script setup>
import { computed, ref } from "vue";
import SheetCodelistOptions from "./SheetCodelistOptions.vue";

// Sets one value in every selected row: picking from the list applies it
// straight away; a typed value applies with Enter or the Set button.
const props = defineProps({
  column: { type: Object, required: true },
  codelists: { type: Object, required: true },
});
const emit = defineEmits(["fill"]);

const text = ref("");
const label = computed(() => `Fill ${props.column.label} in the selected rows`);

function pick(e) {
  const value = e.target.value;
  // Back to the prompt, so the same value can be picked again.
  e.target.value = "";
  emit("fill", value === "__empty__" ? "" : value);
}

function fill() {
  emit("fill", text.value);
  text.value = "";
}
</script>

<template>
  <select v-if="column.kind === 'codelist'" class="sheet-fill" value="" :aria-label="label" @change="pick">
    <option value="">Set for selected…</option>
    <option value="__empty__">(empty)</option>
    <SheetCodelistOptions :column="column" :codelists="codelists" />
  </select>
  <div v-else class="sheet-fill-text">
    <input
      v-model="text"
      class="sheet-fill"
      placeholder="Set for selected…"
      :aria-label="label"
      @keydown.enter.prevent="fill"
    />
    <button type="button" class="sheet-fill-button" :title="label" @click="fill">Set</button>
  </div>
</template>

<style scoped>
.sheet-fill {
  width: 100%;
  min-height: 1.6rem;
  padding: 0 0.5rem;
  border: 1px dashed #bfdbfe;
  border-radius: 4px;
  background: #fff;
  font: inherit;
  font-size: 0.8rem;
  font-weight: 400;
}

select.sheet-fill {
  padding: 0 0.25rem;
  cursor: pointer;
  appearance: auto;
}

.sheet-fill:focus {
  outline: 2px solid #3b82f6;
  outline-offset: -2px;
}

.sheet-fill-text {
  display: flex;
  gap: 0.2rem;
}

.sheet-fill-text .sheet-fill {
  min-width: 0;
}

.sheet-fill-button {
  flex-shrink: 0;
  padding: 0 0.4rem;
  border: 1px solid #bfdbfe;
  border-radius: 4px;
  background: #fff;
  color: #1d4ed8;
  font: inherit;
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
}

.sheet-fill-button:hover {
  background: #dbeafe;
}
</style>
