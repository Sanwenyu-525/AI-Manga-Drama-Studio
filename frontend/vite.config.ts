import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1", // bind IPv4 only (avoids ::1 EACCES on some Windows setups)
    port: 17821, // NOTE: 5173 sits in a Windows excluded port range (5141-5240, Hyper-V/WSL) → EACCES 10013
    proxy: {
      // All /api calls go to the local FastAPI backend (api-event-contract §4).
      "/api": {
        target: "http://127.0.0.1:17820",
        changeOrigin: true,
      },
    },
  },
});
