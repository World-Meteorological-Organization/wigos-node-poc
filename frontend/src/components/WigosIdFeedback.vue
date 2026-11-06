<script setup>
import { computed } from "vue";
import { WIGOS_ID_PATTERN } from "../wmdr";

// Format, duplicate and availability feedback shown under a WigosIdInput.
// `status` comes from useWigosIdAvailability.
const props = defineProps({
  id: { type: String, default: "" },
  status: { type: String, default: null },
  duplicate: Boolean,
});

const MESSAGES = {
  checking: { text: "Checking availability...", color: "text-medium-emphasis" },
  available: { text: "Identifier is available.", color: "text-success" },
  taken: { text: "This WIGOS identifier is already registered to another station.", color: "text-error" },
  error: { text: "Couldn't check availability. It will be checked again on save.", color: "text-medium-emphasis" },
};

const message = computed(() => {
  if (props.id && !WIGOS_ID_PATTERN.test(props.id)) {
    return {
      text: 'Select a country, and enter a numeric issue number and a local identifier (letters, numbers, ".", "_" or "-").',
      color: "text-error",
    };
  }
  if (props.duplicate) return { text: "This identifier is entered more than once in this form.", color: "text-error" };
  return MESSAGES[props.status] ?? null;
});
</script>

<template>
  <div v-if="message" :class="['field-message', message.color]">{{ message.text }}</div>
</template>
