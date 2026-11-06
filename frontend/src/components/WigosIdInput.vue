<script setup>
import { computed } from "vue";
import { splitWigosId, joinWigosId } from "../wmdr";

// A WIGOS station identifier entered as its four parts: a fixed scheme (0),
// the issuer country from ISO3166, the issue number and the local identifier.
const props = defineProps({
  issuerCountries: { type: Array, required: true },
  disabled: Boolean,
  labelPrefix: { type: String, default: "" },
});
const value = defineModel({ type: String, required: true });

const parts = computed(() => splitWigosId(value.value));
const setPart = (part, text) => {
  value.value = joinWigosId({ ...parts.value, [part]: text ?? "" });
};

const issuerItems = computed(() =>
  props.issuerCountries.map((country) => ({
    title: `${country.code} — ${country.label}`,
    value: String(Number(country.code)),
  }))
);
</script>

<template>
  <div class="wigos-id-row">
    <v-text-field
      class="wigos-id-scheme"
      label="Scheme"
      :model-value="parts.scheme"
      disabled
      :aria-label="`${labelPrefix}Identifier scheme`"
      title="Identifier scheme (always 0 for a WIGOS station identifier)"
    />
    <v-autocomplete
      label="Issuer"
      placeholder="Select a country"
      :items="issuerItems"
      :model-value="parts.issuer || null"
      :disabled="disabled"
      :aria-label="`${labelPrefix}Issuer ID`"
      @update:model-value="(issuer) => setPart('issuer', issuer)"
    />
    <v-text-field
      label="Issue number"
      :model-value="parts.issue"
      :disabled="disabled"
      :aria-label="`${labelPrefix}Issue number`"
      @update:model-value="(issue) => setPart('issue', issue)"
    />
    <v-text-field
      label="Local identifier"
      :model-value="parts.local"
      :disabled="disabled"
      :aria-label="`${labelPrefix}Local identifier`"
      @update:model-value="(local) => setPart('local', local)"
    />
  </div>
</template>

<style scoped>
.wigos-id-row {
  display: grid;
  grid-template-columns: 5rem minmax(10rem, 2fr) minmax(6rem, 1fr) minmax(6rem, 1.2fr);
  gap: 0.5rem;
  flex: 1;
  min-width: 0;
}
</style>
