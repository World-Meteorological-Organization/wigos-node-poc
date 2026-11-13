import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import vuetify from "vite-plugin-vuetify";

// Django host the dev server proxies /api, /admin and /static to. Override with
// VITE_PROXY_TARGET (e.g. http://backend:8000 inside docker-compose).
const proxyTarget = process.env.VITE_PROXY_TARGET || "http://127.0.0.1:8000";

// Host the node is reached at through Traefik; Vite answers only known hosts.
const publicHost = new URL(process.env.WIGOS_NODE_URL || "http://localhost").hostname;

export default defineConfig({
  // autoImport registers only the Vuetify components the templates use.
  plugins: [vue(), vuetify({ autoImport: true })],
  test: {
    setupFiles: ["./src/testSetup.js"],
    // Vuetify's ES modules import their CSS; inlining lets Vite handle it.
    server: { deps: { inline: ["vuetify"] } },
  },
  server: {
    host: true,
    port: 5173,
    allowedHosts: [publicHost],
    watch: {
      usePolling: true,
    },
    // No /admin: the Django admin isn't reachable through the frontend (use
    // 127.0.0.1:8000/admin on the server, e.g. through an SSH tunnel).
    proxy: {
      "/api": { target: proxyTarget, changeOrigin: true },
      "/static": { target: proxyTarget, changeOrigin: true },
    },
  },
});
