<script setup>
import ConceptField from "./ConceptField.vue";
import IntervalField from "./IntervalField.vue";
import DurationField from "./DurationField.vue";
import StringListField from "./StringListField.vue";
import ObjectArrayField from "./ObjectArrayField.vue";

// The inputs for one object, one per entry of `fields`. Nested objects are
// edited inline; nested object lists are shown as summaries that open in the
// drill-in dialog.
defineProps({
  fields: { type: Array, required: true },
  path: { type: Array, required: true },
});
const item = defineModel("item", { type: Object, required: true });

const INPUT_TYPES = ["text", "date", "datetime-local"];

const setField = (name, value) => {
  item.value = { ...item.value, [name]: value };
};
const fieldLabel = (field) => (field.required ? `${field.label} *` : field.label);
</script>

<template>
  <template v-for="field in fields" :key="field.name">
    <v-text-field
      v-if="INPUT_TYPES.includes(field.type)"
      class="mb-3"
      :label="fieldLabel(field)"
      :type="field.type"
      :model-value="item[field.name] || ''"
      :placeholder="field.placeholder"
      :persistent-placeholder="!!field.placeholder"
      @update:model-value="(value) => setField(field.name, value)"
    />
    <ConceptField
      v-else-if="field.type === 'concept'"
      class="mb-3"
      :label="field.label"
      :model-value="item[field.name]"
      :options="field.options"
      :groups="field.groups"
      :required="field.required"
      :placeholder="field.placeholder"
      @update:model-value="(value) => setField(field.name, value)"
    />
    <IntervalField
      v-else-if="field.type === 'interval'"
      :label="field.label"
      :days-only="field.daysOnly"
      :start="item[field.start] || ''"
      :end="item[field.end] || ''"
      @update:start="(value) => setField(field.start, value)"
      @update:end="(value) => setField(field.end, value)"
    />
    <DurationField
      v-else-if="field.type === 'duration'"
      :label="field.label"
      :model-value="item[field.name] || ''"
      @update:model-value="(value) => setField(field.name, value)"
    />
    <StringListField
      v-else-if="field.type === 'array-string'"
      :label="field.label"
      :model-value="item[field.name] || []"
      :placeholder="field.placeholder"
      :required="field.required"
      @update:model-value="(value) => setField(field.name, value)"
    />
    <div v-else-if="field.type === 'object'" class="nested-card">
      <div class="nested-card-header">
        <span>{{ field.label }}</span>
      </div>
      <ObjectArrayItemRow
        :item="item[field.name] || {}"
        :fields="field.fields"
        :path="[...path, field.name]"
        @update:item="(value) => setField(field.name, value)"
      />
    </div>
    <ObjectArrayField
      v-else
      :label="field.label"
      :item-label="field.label"
      :model-value="item[field.name] || []"
      :fields="field.fields"
      :item-summary="field.summary"
      mode="summary"
      :path="[...path, field.name]"
      :max-items="field.maxItems"
      :required="field.required"
      @update:model-value="(value) => setField(field.name, value)"
    />
  </template>
</template>
