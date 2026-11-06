<script setup>
import { computed, ref, watch } from "vue";

// An ISO 8601 duration (e.g. PT10M) edited as a number and a unit, with a few
// one-click values. A stored value that isn't one number and one unit (e.g.
// P1DT6H) is kept until another is entered.
defineProps({ label: { type: String, required: true } });
const duration = defineModel({ type: String, default: "" });

// `time` units go after the "T" (PT10M is 10 minutes, P1M is 1 month).
const UNITS = [
  { value: "S", time: true, title: "seconds" },
  { value: "M", time: true, title: "minutes" },
  { value: "H", time: true, title: "hours" },
  { value: "D", time: false, title: "days" },
  { value: "W", time: false, title: "weeks" },
  { value: "MO", time: false, title: "months" },
  { value: "Y", time: false, title: "years" },
];
const PRESETS = [
  { value: "PT30M", title: "30m", tooltip: "30 minutes" },
  { value: "PT1H", title: "1H", tooltip: "1 hour" },
  { value: "PT3H", title: "3H", tooltip: "3 hours" },
  { value: "PT6H", title: "6H", tooltip: "6 hours" },
  { value: "PT12H", title: "12H", tooltip: "12 hours" },
  { value: "P1D", title: "1D", tooltip: "1 day" },
  { value: "P1M", title: "1M", tooltip: "1 month" },
];

const toDuration = (amount, unit) =>
  unit.time ? `PT${amount}${unit.value}` : `P${amount}${unit.value === "MO" ? "M" : unit.value}`;

function fromDuration(value) {
  const match = /^P(T)?(\d+(?:\.\d+)?)([YMWDHS])$/.exec(value || "");
  if (!match) return null;
  const [, time, amount, letter] = match;
  const unit = UNITS.find((u) => u.time === Boolean(time) && (u.value === letter || (letter === "M" && !time && u.value === "MO")));
  return unit && (unit.value === "S" || !amount.includes(".")) ? { amount, unit: unit.value } : null;
}

const amount = ref("");
const unit = ref(null);
watch(
  duration,
  (value) => {
    const parsed = fromDuration(value);
    if (parsed) [amount.value, unit.value] = [parsed.amount, parsed.unit];
    else if (value) amount.value = "";
  },
  { immediate: true }
);

const amountError = computed(() => {
  const text = String(amount.value ?? "").trim();
  if (!text) return null;
  const pattern = unit.value === "S" ? /^\d+(\.\d+)?$/ : /^\d+$/;
  if (!pattern.test(text)) return unit.value === "S" ? "Enter a number" : "Enter a whole number";
  return Number(text) > 0 ? null : "Enter a number above 0";
});
const unitError = computed(() => (String(amount.value ?? "").trim() && !unit.value ? "Choose a unit" : null));
const isCustom = computed(() => !!duration.value && !fromDuration(duration.value));

// Writes the duration once both parts are valid; clearing the number clears it.
function update() {
  const text = String(amount.value ?? "").trim();
  if (!text) duration.value = "";
  else if (unit.value && !amountError.value) duration.value = toDuration(text, UNITS.find((u) => u.value === unit.value));
}
</script>

<template>
  <div class="mb-3">
    <div class="group-label">{{ label }}</div>
    <div class="duration-inputs">
      <v-text-field
        class="duration-amount"
        label="Every"
        type="number"
        min="0"
        :model-value="amount"
        :error-messages="amountError || []"
        @update:model-value="(value) => ((amount = value ?? ''), update())"
      />
      <v-select
        class="duration-unit"
        label="Unit"
        :items="UNITS"
        :model-value="unit"
        :error-messages="unitError || []"
        @update:model-value="(value) => ((unit = value), update())"
      />
      <div class="duration-presets">
        <v-chip
          v-for="preset in PRESETS"
          :key="preset.value"
          size="x-small"
          :color="duration === preset.value ? 'primary' : undefined"
          :variant="duration === preset.value ? 'flat' : 'outlined'"
          :title="preset.tooltip"
          @click="duration = preset.value"
        >
          {{ preset.title }}
        </v-chip>
      </div>
    </div>
    <div v-if="isCustom" class="duration-note">Stored as {{ duration }}; enter a value to replace it.</div>
  </div>
</template>

<style scoped>
.duration-inputs {
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.duration-amount {
  flex: 0 0 110px;
}

.duration-unit {
  flex: 0 0 140px;
}

.duration-presets {
  display: flex;
  gap: 0.25rem;
  padding-top: 0.55rem;
}

.duration-note {
  font-size: 0.85rem;
  color: #475569;
}
</style>
