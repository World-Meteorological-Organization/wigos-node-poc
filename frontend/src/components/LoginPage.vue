<script setup>
import { ref } from "vue";
import { login } from "../auth";

const emit = defineEmits(["success"]);

const username = ref("");
const password = ref("");
const error = ref(null);
const busy = ref(false);

async function handleSubmit() {
  busy.value = true;
  error.value = null;
  try {
    emit("success", await login(username.value, password.value));
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <v-card class="login-card pa-6" max-width="420">
    <v-form @submit.prevent="handleSubmit">
      <h3>Sign in</h3>
      <v-alert v-if="error" type="error" variant="tonal" density="compact" class="mb-4">{{ error }}</v-alert>

      <v-text-field
        v-model="username"
        label="Email or username"
        autocomplete="username"
        autofocus
        class="mb-4"
      />
      <v-text-field
        v-model="password"
        label="Password"
        type="password"
        autocomplete="current-password"
        class="mb-4"
      />

      <v-btn type="submit" color="primary" :loading="busy" :disabled="!username || !password">Sign in</v-btn>
    </v-form>
  </v-card>
</template>

<style scoped>
.login-card {
  margin: 0 auto;
}
</style>
