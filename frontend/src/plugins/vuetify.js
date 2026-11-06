import "@mdi/font/css/materialdesignicons.css";
import "vuetify/styles";
import { createVuetify } from "vuetify";

// Dropdown lists render only the rows in view, and a menu otherwise sizes to
// its widest rendered row, so it would grow and shrink while scrolling. A
// fixed width stops that; a wider field still widens the menu to match.
// Longer entries are cut off with an ellipsis.
const DROPDOWN_MENU = { width: 420 };

// Colours follow the app's blue palette (see app.css). Vuetify's own CSS sits
// in cascade layers, so app.css and scoped styles (unlayered) win over it.
export default createVuetify({
  theme: {
    // Vuetify 4 defaults to "system"; the app has no dark design yet.
    defaultTheme: "light",
    themes: {
      light: {
        colors: {
          primary: "#2563eb",
          secondary: "#1d4ed8",
          background: "#eff6ff",
          surface: "#ffffff",
          error: "#dc2626",
          success: "#059669",
          warning: "#d97706",
          info: "#3b82f6",
        },
      },
    },
  },
  // Compact by default: the station form is long.
  defaults: {
    VTextField: { variant: "outlined", density: "compact", hideDetails: "auto" },
    VTextarea: { variant: "outlined", density: "compact", hideDetails: "auto" },
    VSelect: { variant: "outlined", density: "compact", hideDetails: "auto", menuProps: DROPDOWN_MENU },
    VAutocomplete: { variant: "outlined", density: "compact", hideDetails: "auto", menuProps: DROPDOWN_MENU },
    VCombobox: { variant: "outlined", density: "compact", hideDetails: "auto" },
    VCheckbox: { density: "compact", hideDetails: "auto" },
    VDataTable: { density: "compact" },
    VTable: { density: "compact" },
    VCard: { rounded: "lg" },
    VBtn: { rounded: "lg" },
  },
});
