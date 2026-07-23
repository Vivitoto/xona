/// <reference types="vitest" />

import react from "@vitejs/plugin-react";
import { configDefaults, defineConfig } from "vitest/config";

const backendProxyTarget = process.env.VITE_BACKEND_PROXY_TARGET;

export default defineConfig({
  plugins: [react()],
  server: backendProxyTarget
    ? {
        proxy: {
          "/api": {
            target: backendProxyTarget,
            changeOrigin: true,
          },
        },
      }
    : undefined,
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    exclude: [...configDefaults.exclude, "e2e/**"]
  }
});
