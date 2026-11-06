export const MAPBOX_TILE_URL =
  "https://api.mapbox.com/styles/v1/wmowis/cmmdlz8nb004m01scaoyh6boo/tiles/{z}/{x}/{y}?access_token=pk.eyJ1Ijoid21vd2lzIiwiYSI6ImNtbWRrdTZwbDA0NXMyc3F1ZnN1enVkOG4ifQ.bArk5X6_yvpknSC_Mplpew";
export const MAPBOX_ATTRIBUTION =
  '&copy; <a href="https://www.mapbox.com/about/maps/">Mapbox</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
// Mapbox serves 512px tiles; Leaflet defaults to 256px, so zoomOffset keeps zoom levels aligned.
export const MAPBOX_TILE_SIZE = 512;
export const MAPBOX_ZOOM_OFFSET = -1;
