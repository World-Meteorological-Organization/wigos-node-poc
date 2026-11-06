<script>
// Edits a codelist concept ({ id, title?, description?, url? }). With
// `options` or `groups` (entries from getCodelist) it renders a select that
// fills every property from the codelist (a type-to-filter autocomplete for
// long lists); otherwise a text input for the codelist notation, with the
// other properties behind a "Details" toggle, for codelists that aren't
// cached locally yet.

const optionValue = (opt) => opt.id || opt.code;

function conceptFromOption(opt) {
  const concept = { id: opt.code, title: opt.label };
  if (opt.description) concept.description = opt.description;
  if (opt.id) concept.url = opt.id;
  return concept;
}

// Match on the concept URI first: notations can collide across codelists
// (e.g. "12244" is both an atmosphere and an ocean variable).
function findOption(allOptions, concept) {
  if (!concept) return null;
  return (
    (concept.url && allOptions.find((opt) => opt.id === concept.url)) ||
    allOptions.find((opt) => opt.code === concept.id) ||
    null
  );
}

// Every whitespace-separated term has to appear in the label or notation.
function matchesQuery(opt, query) {
  const haystack = `${opt.label} ${opt.code}`.toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((term) => haystack.includes(term));
}

const DETAIL_FIELDS = [
  { name: "title", label: "Title" },
  { name: "url", label: "URL", placeholder: "Concept URI" },
  { name: "description", label: "Description" },
];

// Codelists longer than this get a type-to-filter box instead of a select.
const SEARCHABLE_MIN_OPTIONS = 15;
// Stands for a value that isn't in the codelist (or while it's still loading).
const CURRENT = "__current__";
</script>

<script setup>
import { computed, ref } from "vue";

const props = defineProps({
  label: { type: String, required: true },
  options: Array,
  groups: Array,
  required: Boolean,
  placeholder: String,
});
const concept = defineModel({ type: Object, default: null });

const fieldLabel = computed(() => (props.required ? `${props.label} *` : props.label));

// --- Codelist (select / autocomplete)

const allOptions = computed(() => (props.groups ? props.groups.flatMap((group) => group.options) : props.options || []));
const selected = computed(() => findOption(allOptions.value, concept.value));
const searchable = computed(() => allOptions.value.length > SEARCHABLE_MIN_OPTIONS);

const toItem = (opt) => ({ title: opt.label, value: optionValue(opt), opt });
const items = computed(() => {
  const list = [];
  // Keep a value that isn't in the codelist (or while it's still loading) visible.
  if (!selected.value && concept.value?.id) {
    const label = concept.value.title || concept.value.id;
    list.push({ title: label, value: CURRENT, opt: { label, code: concept.value.id } });
  }
  if (props.groups) {
    props.groups.forEach((group) => {
      if (!group.options.length) return;
      list.push({ type: "subheader", title: group.label });
      list.push(...group.options.map(toItem));
    });
  } else {
    list.push(...(props.options || []).map(toItem));
  }
  return list;
});
const selectedValue = computed(() => (selected.value ? optionValue(selected.value) : concept.value?.id ? CURRENT : null));

function choose(value) {
  if (value == null) {
    concept.value = null;
    return;
  }
  const opt = allOptions.value.find((o) => optionValue(o) === value);
  if (opt) concept.value = conceptFromOption(opt);
}

const filter = (_value, query, item) => !item.raw.opt || matchesQuery(item.raw.opt, query);

// --- Free text (no codelist)

const showDetails = ref(DETAIL_FIELDS.some((field) => concept.value?.[field.name]));

function updateFreeText(key, text) {
  const next = { ...(concept.value || { id: "" }), [key]: text ?? "" };
  Object.keys(next).forEach((k) => {
    if (k !== "id" && !next[k]) delete next[k];
  });
  concept.value = Object.values(next).some(Boolean) ? next : null;
}
</script>

<template>
  <div v-if="!options && !groups">
    <div class="input-row">
      <v-text-field
        :label="fieldLabel"
        :model-value="concept?.id || ''"
        :placeholder="placeholder"
        :persistent-placeholder="!!placeholder"
        @update:model-value="(text) => updateFreeText('id', text)"
      />
      <v-btn variant="outlined" :aria-expanded="showDetails" @click="showDetails = !showDetails">
        {{ showDetails ? "Hide details" : "Details" }}
      </v-btn>
    </div>
    <template v-if="showDetails">
      <v-text-field
        v-for="field in DETAIL_FIELDS"
        :key="field.name"
        class="mt-2"
        :label="field.label"
        :model-value="concept?.[field.name] || ''"
        :placeholder="field.placeholder"
        @update:model-value="(text) => updateFreeText(field.name, text)"
      />
    </template>
  </div>

  <v-autocomplete
    v-else-if="searchable"
    :label="fieldLabel"
    placeholder="Type to filter"
    :items="items"
    :model-value="selectedValue"
    :custom-filter="filter"
    auto-select-first
    clearable
    @update:model-value="choose"
  >
    <template #item="{ item, props: itemProps }">
      <v-list-item v-bind="itemProps">
        <template v-if="item.opt.code !== item.opt.label" #append>
          <span class="concept-code">{{ item.opt.code }}</span>
        </template>
      </v-list-item>
    </template>
  </v-autocomplete>

  <v-select
    v-else
    :label="fieldLabel"
    placeholder="None selected"
    :items="items"
    :model-value="selectedValue"
    clearable
    @update:model-value="choose"
  />
</template>

<style scoped>
.concept-code {
  margin-left: 0.75rem;
  font-size: 0.8rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
</style>
