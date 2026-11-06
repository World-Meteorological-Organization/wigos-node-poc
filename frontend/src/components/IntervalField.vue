<script setup>
import { computed, reactive } from "vue";
import { OPEN, dayFromPicker, describeInterval, intervalError, pickerFromDay, readBound } from "../interval";

// A From – To interval. Bounds are typed freely and the interval is read back
// below ("Since January 2020, ongoing"); a calendar picks a day; "Unknown" /
// "Ongoing" store an open bound (".."). `daysOnly` restricts bounds to full
// dates, as affiliation and territory dates require.
const props = defineProps({
  label: { type: String, required: true },
  daysOnly: Boolean,
});
const start = defineModel("start", { type: String, default: "" });
const end = defineModel("end", { type: String, default: "" });

const options = computed(() => ({ daysOnly: props.daysOnly }));
const pickerOpen = reactive({ start: false, end: false });

const bounds = computed(() => [
  { key: "start", model: start, label: "From", openLabel: "Unknown" },
  { key: "end", model: end, label: "To", openLabel: "Ongoing" },
]);

const rangeError = computed(() => intervalError(start.value, end.value, options.value));
const summary = computed(() => describeInterval(start.value, end.value, options.value));

const isOpen = (bound) => bound.model.value === OPEN;
function errorsOf(bound) {
  const read = readBound(bound.model.value, options.value);
  if (read.kind === "invalid") return [read.message];
  return bound.key === "end" && rangeError.value ? [rangeError.value] : [];
}

const set = (bound, value) => (bound.model.value = value);
function pick(bound, value) {
  set(bound, dayFromPicker(value));
  pickerOpen[bound.key] = false;
}
</script>

<template>
  <div class="interval-field mb-3">
    <div class="group-label">{{ label }}</div>
    <div class="interval-bounds">
      <template v-for="(bound, i) in bounds" :key="bound.key">
        <span v-if="i > 0" class="interval-dash" aria-hidden="true">–</span>
        <div class="interval-bound">
          <v-text-field
            :label="bound.label"
            :model-value="isOpen(bound) ? '' : bound.model.value"
            :disabled="isOpen(bound)"
            :placeholder="isOpen(bound) ? '' : daysOnly ? 'YYYY-MM-DD' : 'e.g. 2020, 2020-01, 2020-01-31'"
            :persistent-placeholder="!isOpen(bound)"
            :error-messages="errorsOf(bound)"
            @update:model-value="(value) => set(bound, value)"
          >
            <template #append-inner>
              <v-menu v-model="pickerOpen[bound.key]" :close-on-content-click="false">
                <template #activator="{ props: activator }">
                  <v-btn
                    v-bind="activator"
                    icon="mdi-calendar"
                    variant="text"
                    size="small"
                    density="comfortable"
                    :disabled="isOpen(bound)"
                    :aria-label="`Pick the ${bound.label.toLowerCase()} date`"
                  />
                </template>
                <v-date-picker
                  :model-value="pickerFromDay(bound.model.value)"
                  show-adjacent-months
                  @update:model-value="(value) => pick(bound, value)"
                />
              </v-menu>
            </template>
          </v-text-field>
          <v-checkbox
            :label="bound.openLabel"
            :model-value="isOpen(bound)"
            @update:model-value="(checked) => set(bound, checked ? OPEN : '')"
          />
        </div>
      </template>
    </div>
    <div v-if="summary" class="interval-summary">{{ summary }}</div>
  </div>
</template>

<style scoped>
.interval-bounds {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
}

.interval-bound {
  flex: 1;
  min-width: 0;
}

.interval-dash {
  padding-top: 0.6rem;
  color: #64748b;
}

.interval-summary {
  font-size: 0.85rem;
  color: #475569;
}

@media (max-width: 600px) {
  .interval-bounds {
    flex-direction: column;
    align-items: stretch;
  }

  .interval-dash {
    display: none;
  }
}
</style>
