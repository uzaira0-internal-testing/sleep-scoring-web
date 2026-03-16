import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import wasm from "vite-plugin-wasm";
import { VitePWA } from "vite-plugin-pwa";
import { resolve } from "path";
import { readFileSync } from "fs";
import { visualizer } from "rollup-plugin-visualizer";
import viteCompression from "vite-plugin-compression";

// Tauri expects a fixed port for dev, and internalHost for mobile
const host = process.env.TAURI_DEV_HOST;

// Read version from package.json at build time
const pkg = JSON.parse(readFileSync(resolve(__dirname, "package.json"), "utf-8"));

export default defineConfig({
  plugins: [
    tailwindcss(),
    react(),
    wasm(),
    // Bundle analysis: ANALYZE=1 npx vite build → opens treemap
    ...(process.env.ANALYZE ? [visualizer({ open: true, gzipSize: true, brotliSize: true, filename: "dist/stats.html" })] : []),
    viteCompression({ algorithm: "gzip", threshold: 1024 }),
    viteCompression({ algorithm: "brotliCompress", threshold: 1024, ext: ".br" }),
    VitePWA({
      // DISABLED: SW + BASE_PATH causes stale cache issues on deployment.
      // The self-healing script in index.html unregisters old SWs.
      // Re-enable once BASE_PATH-aware SW registration is implemented.
      selfDestroying: true,
      manifest: false,
    }),
  ],
  base: "./",
  resolve: {
    alias: {
      "@": resolve(__dirname, "./src"),
    },
  },
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  build: {
    outDir: "dist",
    sourcemap: process.env.TAURI_ENV_DEBUG ? true : "hidden",
    target: "esnext",
    minify: "terser",
    terserOptions: {
      compress: { passes: 2, drop_console: true, drop_debugger: true },
      mangle: true,
    },
    rollupOptions: {
      // Tauri-only plugins are dynamically imported and only resolve at runtime in the desktop app.
      // Externalize them so the web/Docker build doesn't fail when they're not installed.
      external: ["@tauri-apps/plugin-process", "@tauri-apps/plugin-updater"],
      output: {
        manualChunks(id: string): string | undefined {
          if (id.includes("node_modules")) {
            // Libraries with no React dependency — safe to split
            if (id.includes("uplot")) return "uplot";
            if (id.includes("dexie")) return "dexie";
            if (id.includes("zod")) return "zod";
            if (id.includes("/date-fns/")) return "date-fns";
            // Upload libs — only needed on upload page
            if (id.includes("@uppy") || id.includes("tus-js-client")) return "upload";
            // Everything else (react, react-dom, tanstack, lucide, etc.)
            return "vendor";
          }
        },
      },
    },
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
