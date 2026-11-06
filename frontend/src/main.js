import { createApp } from "vue";
import App from "./App.vue";
import vuetify from "./plugins/vuetify";
import "leaflet/dist/leaflet.css";
import "./app.css";

createApp(App).use(vuetify).mount("#app");
