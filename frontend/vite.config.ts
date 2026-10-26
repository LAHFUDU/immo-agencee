/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// In development the API runs on :8000; Vite proxies /api so cookies stay same-origin.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.VITE_API_PROXY ?? "http://localhost:8000", changeOrigin: false } },
  },
  build: { sourcemap: false, chunkSizeWarningLimit: 900 },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/test/setup.ts"] },
});
