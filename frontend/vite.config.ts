/// <reference types="vitest/config" />
import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const proxyTarget = process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/auth": proxyTarget,
      "/briefings": proxyTarget,
      "/status": proxyTarget,
      "/mcp": proxyTarget,
      "/voice": proxyTarget,      // Fase 6b
      "/memories": proxyTarget,   // Fase 6b
      "/audit": proxyTarget,      // Fase 7
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/__tests__/setup.ts"],
    globals: true,
  },
});
