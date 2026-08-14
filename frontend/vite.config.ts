import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // All /api calls go to the local FastAPI backend (api-event-contract §4).
      "/api": {
        target: "http://127.0.0.1:17820",
        changeOrigin: true,
      },
    },
  },
});
