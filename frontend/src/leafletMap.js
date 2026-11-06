import L from "leaflet";
import { MAPBOX_TILE_URL, MAPBOX_ATTRIBUTION, MAPBOX_TILE_SIZE, MAPBOX_ZOOM_OFFSET } from "./mapConfig";

export const DEFAULT_CENTER = [20, 0];
export const DEFAULT_ZOOM = 2;
export const MARKER_STYLE = { color: "#1d4ed8", weight: 1, fillColor: "#3b82f6", fillOpacity: 0.9 };

// A Leaflet map on `element` with the Mapbox base layer.
export function createBaseMap(element, { center = DEFAULT_CENTER, zoom = DEFAULT_ZOOM } = {}) {
  const map = L.map(element, { center, zoom, attributionControl: false });
  L.tileLayer(MAPBOX_TILE_URL, {
    attribution: MAPBOX_ATTRIBUTION,
    tileSize: MAPBOX_TILE_SIZE,
    zoomOffset: MAPBOX_ZOOM_OFFSET,
  }).addTo(map);
  L.control.attribution({ prefix: "Leaflet" }).addTo(map);
  return map;
}
