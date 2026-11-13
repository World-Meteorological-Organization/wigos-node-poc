<script setup>
import { computed, onUnmounted, ref, watch } from "vue";
import { listPublications } from "./api";
import LoginPage from "./components/LoginPage.vue";
import PublicationsPage from "./components/PublicationsPage.vue";
import StationsList from "./components/StationsList.vue";
import WmdrForm from "./components/WmdrForm.vue";
import BatchWizard from "./components/batch/BatchWizard.vue";
import { useAuth } from "./composables/useAuth";

const { status, user, setUser, logout } = useAuth();

// { mode: "list" | "new" | "edit" | "batch" | "publications", stationId?, stationIds? }
const view = ref({ mode: "list" });
// Station IDs ticked in the list; kept here so they survive the batch wizard.
const selected = ref(new Set());

// The sidebar is for the main pages; the form and the wizard have their own way out.
const NAV_ITEMS = [
  { mode: "list", title: "Stations", icon: "mdi-map-marker-multiple" },
  { mode: "publications", title: "Publishing", icon: "mdi-history" },
];
const showNav = computed(() => status.value === "authenticated" && NAV_ITEMS.some((item) => item.mode === view.value.mode));
// null: open on large screens, closed on small ones (Vuetify's default)
const navOpen = ref(null);

// Failed stations the user can edit, on the Publishing item. It only shows with
// the sidebar, so it is only kept up to date then.
const FAILURES_REFRESH_MS = 30000;
const failures = ref(0);
let failuresTimer = null;
let failuresRequests = 0;

async function refreshFailures() {
  const request = ++failuresRequests;
  try {
    const { count } = await listPublications({ status: "failed", limit: 1 });
    // A slower, older answer must not replace a newer one.
    if (request === failuresRequests) failures.value = count;
  } catch {
    // keeps the last number: the rest of the app works without it
  }
}

watch(showNav, (shown) => {
  clearInterval(failuresTimer);
  if (shown) {
    refreshFailures();
    failuresTimer = setInterval(refreshFailures, FAILURES_REFRESH_MS);
  }
}, { immediate: true });
onUnmounted(() => clearInterval(failuresTimer));

async function handleLogout() {
  await logout();
  view.value = { mode: "list" };
  selected.value = new Set();
  failures.value = 0;
}
</script>

<template>
  <v-app>
    <v-app-bar class="app-bar" height="100" flat>
      <template v-if="showNav" #prepend>
        <v-app-bar-nav-icon aria-label="Toggle the menu" @click="navOpen = !navOpen" />
      </template>
      <img class="app-bar-logo" src="./assets/img/logo.png" alt="WMO logo" />
      <div class="app-bar-title">
        <h1>WMDR Station Record Builder</h1>
        <!-- On narrower screens it would run into the dark part of the banner. -->
        <p class="d-none d-lg-block">Fill in station metadata and generate a WMDRv2 conformant record.</p>
      </div>
      <template v-if="status === 'authenticated'" #append>
        <span class="app-bar-user mr-3">{{ user.email || user.username }}</span>
        <v-btn class="app-bar-user" variant="tonal" @click="handleLogout">Log out</v-btn>
      </template>
    </v-app-bar>

    <!-- Before the drawer, so that it spans the whole width below it. -->
    <v-footer class="app-footer" height="12" app />

    <v-navigation-drawer v-if="showNav" v-model="navOpen">
      <v-list nav>
        <v-list-item
          v-for="item in NAV_ITEMS"
          :key="item.mode"
          :title="item.title"
          :prepend-icon="item.icon"
          :active="view.mode === item.mode"
          color="primary"
          @click="view = { mode: item.mode }"
        >
          <template v-if="item.mode === 'publications' && failures > 0" #append>
            <v-chip size="x-small" color="error" variant="flat" :aria-label="`${failures} failed`">{{ failures }}</v-chip>
          </template>
        </v-list-item>
      </v-list>
    </v-navigation-drawer>

    <v-main>
      <v-container :class="['app-main', { 'app-main-wide': view.mode === 'batch' }]">
        <p v-if="status === 'loading'">Loading…</p>

        <LoginPage v-else-if="status === 'anonymous'" @success="setUser" />

        <template v-else>
          <StationsList
            v-if="view.mode === 'list'"
            v-model:selected="selected"
            @new="view = { mode: 'new' }"
            @edit="(stationId) => (view = { mode: 'edit', stationId })"
            @batch="(stationIds) => (view = { mode: 'batch', stationIds })"
            @changed="refreshFailures"
          />
          <WmdrForm
            v-else-if="view.mode === 'new' || view.mode === 'edit'"
            :key="view.mode === 'edit' ? view.stationId : 'new'"
            :station-id="view.mode === 'edit' ? view.stationId : null"
            @saved="view = { mode: 'list' }"
            @cancel="view = { mode: 'list' }"
          />
          <!-- Only the stations that failed stay selected after applying. -->
          <BatchWizard
            v-else-if="view.mode === 'batch'"
            :station-ids="view.stationIds"
            @applied="(failedIds) => (selected = new Set(failedIds))"
            @close="view = { mode: 'list' }"
          />
          <PublicationsPage v-else-if="view.mode === 'publications'" @changed="refreshFailures" />
        </template>
      </v-container>
    </v-main>
  </v-app>
</template>

<style scoped>
/* The clouds, with the coloured stripe below them. The banner is white on the
   left and blue on the right, so the title is dark and the user's details light. */
.app-bar {
  background:
    url("./assets/img/wmo-foot.png") bottom / 100% 12px no-repeat,
    url("./assets/img/wmo-banner.png") top / 100% calc(100% - 12px) no-repeat,
    #fff !important;
  color: #003a78 !important;
  padding: 0 1rem;
}

.app-bar :deep(.v-toolbar__content) {
  padding-bottom: 12px;
}

.app-bar-logo {
  height: 72px;
  margin-right: 1rem;
}

.app-bar-title {
  text-shadow: 0 0 6px rgba(255, 255, 255, 0.9);
}

.app-bar-title h1 {
  color: #003a78;
  font-size: 1.4rem;
  font-weight: 700;
  margin: 0;
}

.app-bar-title p {
  margin: 0.25rem 0 0;
  color: #1f2f46;
  font-size: 0.9rem;
}

.app-bar-user {
  color: #fff;
  text-shadow: 0 0 4px rgba(0, 58, 120, 0.9);
}

.app-footer {
  background: url("./assets/img/wmo-foot.png") center / 100% 100% no-repeat;
  padding: 0;
}

.app-main {
  max-width: 1200px;
  padding: 2rem;
}

/* The batch wizard needs the width for wide grids. */
.app-main-wide {
  max-width: none;
}
</style>
