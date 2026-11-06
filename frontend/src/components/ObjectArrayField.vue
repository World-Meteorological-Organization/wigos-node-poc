<script>
const INPUT_TYPES = ["text", "date", "datetime-local", "duration"];

function emptyValueForField(field) {
  if (field.default !== undefined) return field.default;
  if (INPUT_TYPES.includes(field.type)) return "";
  if (field.type === "concept") return null;
  if (field.type === "object") return emptyItem(field.fields);
  if (field.type === "array-object" && field.required) return [emptyItem(field.fields)];
  return [];
}

// An interval field edits two keys of the item: its `start` and `end`.
function emptyItem(fields) {
  return Object.fromEntries(
    fields.flatMap((field) =>
      field.type === "interval"
        ? [
            [field.start, ""],
            [field.end, ""],
          ]
        : [[field.name, emptyValueForField(field)]]
    )
  );
}
</script>

<script setup>
import { computed, inject, ref } from "vue";
import ObjectArrayItemRow from "./ObjectArrayItemRow.vue";
import { DRILL_INTO } from "./drillInto";
import { useAutoCollapse } from "../composables/useAutoCollapse";

// A list of objects. In "full" mode each item is a card edited inline; in
// "summary" mode each item is a one-line summary that opens in the drill-in
// dialog (see DrillInArrayField).
const props = defineProps({
  label: { type: String, required: true },
  itemLabel: { type: String, required: true },
  fields: { type: Array, required: true },
  itemSummary: Function,
  mode: { type: String, default: "full" },
  path: { type: Array, required: true },
  required: Boolean,
  maxItems: Number,
});
const values = defineModel({ type: Array, required: true });
const drillInto = inject(DRILL_INTO, null);

// All items start collapsed when the form first loads. Items added later
// via "Add" are not in this set, so they start expanded for editing.
const collapsed = ref(new Set(values.value.map((_, i) => i)));

const summaryOf = (item, fallback) => (props.itemSummary && props.itemSummary(item)) || fallback;

const update = (index, next) => {
  values.value = values.value.map((v, i) => (i === index ? next : v));
};
const add = () => {
  values.value = [...values.value, emptyItem(props.fields)];
};
const remove = (index) => {
  values.value = values.value.filter((_, i) => i !== index);
  const next = new Set();
  collapsed.value.forEach((idx) => {
    if (idx < index) next.add(idx);
    else if (idx > index) next.add(idx - 1);
  });
  collapsed.value = next;
};
const toggleCollapsed = (index) => {
  const next = new Set(collapsed.value);
  if (next.has(index)) next.delete(index);
  else next.add(index);
  collapsed.value = next;
};

// Card elements by index, for collapsing the cards focus leaves.
const cardRefs = {};
const setCardRef = (index, element) => {
  cardRefs[index] = element;
};
useAutoCollapse(
  () => cardRefs,
  (keys) => {
    const indices = keys.map(Number).filter((index) => !collapsed.value.has(index));
    if (indices.length) collapsed.value = new Set([...collapsed.value, ...indices]);
  },
  () => props.mode === "full"
);

const atMax = computed(() => props.maxItems != null && values.value.length >= props.maxItems);
</script>

<template>
  <div class="mb-5">
    <div class="group-label">
      {{ label }}<span v-if="required" class="required-mark">*</span>
    </div>

    <template v-if="mode === 'summary'">
      <div v-for="(item, i) in values" :key="i" class="summary-row">
        <span>{{ summaryOf(item, `New ${itemLabel.toLowerCase()}`) }}</span>
        <div class="nested-card-header-actions">
          <v-btn
            variant="tonal"
            color="secondary"
            size="small"
            append-icon="mdi-chevron-right"
            @click="drillInto([...path, i], `${itemLabel} ${i + 1}`, fields)"
          >
            Edit details
          </v-btn>
          <v-btn variant="outlined" size="small" @click="remove(i)">Remove</v-btn>
        </div>
      </div>
    </template>

    <template v-else>
      <div v-for="(item, i) in values" :key="i" :ref="(el) => setCardRef(i, el)" class="nested-card">
        <div class="nested-card-header">
          <span>{{ summaryOf(item, `${itemLabel} ${i + 1}`) }}</span>
          <div class="nested-card-header-actions">
            <v-btn variant="outlined" size="small" :aria-expanded="!collapsed.has(i)" @click="toggleCollapsed(i)">
              {{ collapsed.has(i) ? "Expand" : "Minimize" }}
            </v-btn>
            <v-btn variant="outlined" size="small" @click="remove(i)">Remove</v-btn>
          </div>
        </div>
        <ObjectArrayItemRow
          v-if="!collapsed.has(i)"
          :item="item"
          :fields="fields"
          :path="[...path, i]"
          @update:item="(next) => update(i, next)"
        />
      </div>
    </template>

    <v-btn v-if="!atMax" variant="tonal" color="secondary" size="small" prepend-icon="mdi-plus" @click="add">
      Add {{ itemLabel }}
    </v-btn>
  </div>
</template>
