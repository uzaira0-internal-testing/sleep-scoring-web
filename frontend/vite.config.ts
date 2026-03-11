import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import wasm from "vite-plugin-wasm";
import { VitePWA } from "vite-plugin-pwa";
import { resolve } from "path";

// Tauri expects a fixed port for dev, and internalHost for mobile
const host = process.env.TAURI_DEV_HOST;

export default defineConfig({
  plugins: [
    tailwindcss(),
    react(),
    wasm(),
    VitePWA({
      registerType: "autoUpdate",
      workbox: {
        globPatterns: ["**/*.{js,css,html,wasm,svg,png,ico}"],
        // Only cache API responses when there's a real server behind them.
        // In Tauri, /api/ paths return SPA HTML (asset protocol fallback),
        // which must NOT be cached as API data.
        runtimeCaching: [
          {
            urlPattern: /\/api\//,
            handler: "NetworkFirst",
            options: {
              cacheName: "api-cache",
              expiration: { maxEntries: 50, maxAgeSeconds: 300 },
              cacheableResponse: { headers: { "content-type": "application/json" } },
            },
          },
        ],
      },
      manifest: false, // Using public/manifest.json directly
    }),
  ],
  base: "./",
  resolve: {
    alias: {
      "@": resolve(__dirname, "./src"),
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    target: "esnext",
  },
  optimizeDeps: {
    exclude: ["sleep-scoring-wasm"],
    include: ["@tauri-apps/api/core"],
  },
  worker: {
    format: "es",
    plugins: () => [wasm()],
  },
  server: {
    host: host || false,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://localhost:8500",
        changeOrigin: true,
      },
    },
  },
});
