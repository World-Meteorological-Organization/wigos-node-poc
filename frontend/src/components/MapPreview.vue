<script setup>
import { computed, onBeforeUnmount, onMounted, shallowRef, watch } from "vue";
import L from "leaflet";
import { MARKER_STYLE, createBaseMap } from "../leafletMap";

const props = defineProps({
  latitude: { type: [String, Number], default: "" },
  longitude: { type: [String, Number], default: "" },
});

const POINT_ZOOM = 9;
const MARKER_RADIUS_METERS = 5000;

const position = computed(() => {
  const lat = Number(props.latitude);
  const lon = Number(props.longitude);
  const hasPosition = props.latitude !== "" && props.longitude !== "" && !Number.isNaN(lat) && !Number.isNaN(lon);
  return hasPosition ? [lat, lon] : null;
});

const container = shallowRef(null);
let map = null;
let marker = null;

function showPosition() {
  marker?.remove();
  marker = null;
  if (!position.value) return;
  marker = L.circle(position.value, { radius: MARKER_RADIUS_METERS, ...MARKER_STYLE }).addTo(map);
  map.setView(position.value, POINT_ZOOM);
}

onMounted(() => {
  map = createBaseMap(container.value);
  showPosition();
});
// Compare by value: the computed returns a new array on every change.
watch(() => position.value?.join(","), () => map && showPosition());
onBeforeUnmount(() => map?.remove());
</script>

<template>
  <div>
    <div ref="container" class="map-preview" />
    <p v-if="!position" class="map-hint">Enter latitude/longitude to preview the point.</p>
  </div>
</template>

<style scoped>
.map-preview {
  height: 280px;
  width: 100%;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #e2e8f0;
}

.map-hint {
  margin-top: 0.6rem;
  font-size: 0.85rem;
  color: #64748b;
}
</style>
