<script setup>
import { computed, provide, ref } from "vue";
import ObjectArrayField from "./ObjectArrayField.vue";
import ObjectArrayItemRow from "./ObjectArrayItemRow.vue";
import { DRILL_INTO } from "./drillInto";
import { getAtPath, setAtPath, isFieldsetComplete } from "../formPath";

// A list of objects edited inline, whose nested object lists open in a
// dialog. The dialog keeps a trail, so a list inside a dialog item opens
// another level with a way back.
defineProps({
  label: { type: String, required: true },
  itemLabel: { type: String, required: true },
  fields: { type: Array, required: true },
  itemSummary: Function,
  required: Boolean,
});
const values = defineModel({ type: Array, required: true });

const trail = ref([]);
const current = computed(() => trail.value[trail.value.length - 1]);
const currentItem = computed(() => (current.value && getAtPath(values.value, current.value.path)) || {});

provide(DRILL_INTO, (path, label, fields) => {
  trail.value = [...trail.value, { path, label, fields }];
});
const back = () => {
  trail.value = trail.value.slice(0, -1);
};
const close = () => {
  trail.value = [];
};
const updateCurrent = (next) => {
  values.value = setAtPath(values.value, current.value.path, next);
};
</script>

<template>
  <ObjectArrayField
    v-model="values"
    :label="label"
    :item-label="itemLabel"
    :fields="fields"
    :item-summary="itemSummary"
    mode="full"
    :path="[]"
    :required="required"
  />

  <v-dialog :model-value="!!current" max-width="520" scrollable @update:model-value="(open) => !open && close()">
    <v-card v-if="current">
      <v-card-title class="d-flex align-center">
        <span class="text-truncate">{{ current.label }}</span>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="close" />
      </v-card-title>
      <v-divider />
      <v-card-text>
        <v-btn
          v-if="trail.length > 1"
          class="mb-4"
          variant="text"
          size="small"
          prepend-icon="mdi-chevron-left"
          @click="back"
        >
          Back to {{ trail[trail.length - 2].label }}
        </v-btn>
        <!-- Keyed by path, so moving between levels starts each one fresh. -->
        <ObjectArrayItemRow
          :key="current.path.join('.')"
          :item="currentItem"
          :fields="current.fields"
          :path="current.path"
          @update:item="updateCurrent"
        />
      </v-card-text>
      <v-card-actions v-if="trail.length <= 1">
        <v-btn color="primary" variant="flat" :disabled="!isFieldsetComplete(currentItem, current.fields)" @click="close">
          Done
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
