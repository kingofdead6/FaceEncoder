import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Dev-server proxy: the React app talks to relative /api and /ws paths, and
// Vite forwards them to the FastAPI backend. In production the same paths are
// proxied by nginx (see frontend/nginx.conf), so no code changes are needed.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/ws": { target: "ws://localhost:8000", ws: true, changeOrigin: true },
    },
  },
  build: { outDir: "dist", sourcemap: false },
});
