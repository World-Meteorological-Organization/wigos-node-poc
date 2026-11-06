<script>
import { CONTACT_LINK_FIELDS, LOGO_FIELDS } from "../fieldDefs";

const PHONE_FIELDS = [
  { name: "value", label: "Phone number", type: "text", placeholder: "+41791234567" },
  { name: "roles", label: "Roles", type: "array-string" },
];

const EMAIL_FIELDS = [
  { name: "value", label: "Email address", type: "text", placeholder: "name@example.org" },
  { name: "roles", label: "Roles", type: "array-string" },
];

const ADDRESS_FIELDS = [
  { name: "city", label: "City", type: "text" },
  { name: "administrativeArea", label: "State / province", type: "text" },
  { name: "postalCode", label: "Postal code", type: "text" },
  { name: "country", label: "Country", type: "text" },
  { name: "deliveryPoint", label: "Delivery point lines", type: "array-string" },
  { name: "roles", label: "Roles", type: "array-string" },
];

const CONTACT_FIELDS = [
  { name: "organization", label: "Organization", type: "text", required: true },
  { name: "name", label: "Name", type: "text" },
  { name: "position", label: "Position", type: "text" },
  { name: "identifier", label: "Identifier", type: "text", placeholder: "Unique contact identifier" },
  { name: "phones", label: "Phone", type: "array-object", fields: PHONE_FIELDS, summary: (p) => p.value },
  { name: "emails", label: "Email", type: "array-object", fields: EMAIL_FIELDS, summary: (e) => e.value },
  {
    name: "addresses",
    label: "Address",
    type: "array-object",
    fields: ADDRESS_FIELDS,
    summary: (a) => [a.city, a.country].filter(Boolean).join(", "),
  },
  { name: "links", label: "Link", type: "array-object", fields: CONTACT_LINK_FIELDS, summary: (l) => l.title || l.href },
  { name: "hoursOfService", label: "Hours of service", type: "text" },
  { name: "contactInstructions", label: "Contact instructions", type: "text" },
  { name: "roles", label: "Roles", type: "array-string" },
  { name: "logo", label: "Logo", type: "object", fields: LOGO_FIELDS },
];

const contactSummary = (c) => [c.organization, c.name].filter(Boolean).join(" - ");
</script>

<script setup>
import DrillInArrayField from "./DrillInArrayField.vue";

const contacts = defineModel({ type: Array, required: true });
</script>

<template>
  <DrillInArrayField
    v-model="contacts"
    label="Contacts"
    item-label="Contact"
    :fields="CONTACT_FIELDS"
    :item-summary="contactSummary"
    required
  />
</template>
