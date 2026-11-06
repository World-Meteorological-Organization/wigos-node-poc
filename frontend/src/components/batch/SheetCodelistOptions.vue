<script setup>
import { computed } from "vue";
import { findCodelistOption } from "../../batch/common";
import { CODELISTS, codelistOptions } from "../../codelists";

// The <option>s of a codelist column, grouped like the station form. A value
// that isn't in the codelist is kept as an extra option so it stays visible.
const props = defineProps({
  column: { type: Object, required: true },
  codelists: { type: Object, required: true },
  value: { type: String, default: "" },
});

const list = computed(() => props.codelists[props.column.codelist] || []);
const grouped = computed(() => typeof CODELISTS[props.column.codelist] !== "string");
const unknown = computed(
  () => !!props.value && !findCodelistOption(codelistOptions(props.column.codelist, props.codelists), props.value)
);
const optionText = (opt) => (opt.label === opt.code ? opt.label : `${opt.label} (${opt.code})`);
</script>

<template>
  <option v-if="unknown" :value="value">{{ value }} (not in the codelist)</option>
  <template v-if="grouped">
    <optgroup v-for="group in list" :key="group.label" :label="group.label">
      <option v-for="opt in group.options" :key="`${opt.id}|${opt.code}`" :value="opt.code">{{ optionText(opt) }}</option>
    </optgroup>
  </template>
  <template v-else>
    <option v-for="opt in list" :key="`${opt.id}|${opt.code}`" :value="opt.code">{{ optionText(opt) }}</option>
  </template>
</template>
