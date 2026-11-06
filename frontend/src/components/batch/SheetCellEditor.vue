<script setup>
import { onMounted, ref } from "vue";
import SheetCodelistOptions from "./SheetCodelistOptions.vue";

// The editor of the active cell, a native input or select. Its value is
// held by the grid, so a click elsewhere can commit it. `commit` carries the
// direction to move afterwards (null: stay).
defineProps({
  column: { type: Object, required: true },
  codelists: { type: Object, required: true },
  // The values a key column allows on this row: [{ label }].
  choices: { type: Array, default: null },
});
const value = defineModel({ type: String, required: true });
const emit = defineEmits(["commit", "cancel"]);

const editor = ref(null);

onMounted(() => {
  editor.value?.focus();
  // Open the list straight away; showPicker needs a recent click or key press
  // and isn't supported everywhere, so failures are ignored.
  try {
    if (editor.value?.tagName === "SELECT") editor.value.showPicker?.();
  } catch {
    /* the select is focused, which is enough */
  }
});

function onKeydown(e) {
  if (e.key === "Enter") {
    e.preventDefault();
    emit("commit", e.shiftKey ? "up" : "down");
  } else if (e.key === "Tab") {
    e.preventDefault();
    emit("commit", e.shiftKey ? "left" : "right");
  } else if (e.key === "Escape") {
    e.preventDefault();
    e.stopPropagation();
    emit("cancel");
  }
}
</script>

<template>
  <select
    v-if="choices"
    ref="editor"
    v-model="value"
    class="sheet-editor"
    @blur="emit('commit', null)"
    @keydown="onKeydown"
  >
    <option v-for="(choice, i) in choices" :key="i" :value="choice.label">{{ choice.label }}</option>
  </select>
  <select
    v-else-if="column.kind === 'codelist'"
    ref="editor"
    v-model="value"
    class="sheet-editor"
    @blur="emit('commit', null)"
    @keydown="onKeydown"
  >
    <option value="">(empty)</option>
    <SheetCodelistOptions :column="column" :codelists="codelists" :value="value" />
  </select>
  <input
    v-else
    ref="editor"
    v-model="value"
    class="sheet-editor"
    @blur="emit('commit', null)"
    @keydown="onKeydown"
  />
</template>

<style scoped>
.sheet-editor {
  width: 100%;
  height: 100%;
  min-height: 2rem;
  border: none;
  padding: 0 0.5rem;
  font: inherit;
  background: #fff;
}

select.sheet-editor {
  padding: 0 0.25rem;
  cursor: pointer;
  appearance: auto;
}

.sheet-editor:focus {
  outline: 2px solid #3b82f6;
  outline-offset: -2px;
}
</style>
