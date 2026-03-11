/**
 * Bun-native development server with:
 * - Static file serving
 * - API proxying to backend
 * - Live reload via WebSocket
 * - On-demand bundling
 */

import { watch } from "fs";
import { join, resolve } from "path";

const ROOT_DIR = resolve(import.meta.dir, "..");
const SRC_DIR = join(ROOT_DIR, "src");
const PUBLIC_DIR = join(ROOT_DIR, "public");
const OUT_DIR = join(ROOT_DIR, ".bun-dev");
const PORT = parseInt(process.env.PORT || "5173");
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8500";

// Track connected WebSocket clients for live reload
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const clients = new Set<any>();

// Path alias plugin for @/ -> src/
// Also handles directory imports by resolving to index.ts
const pathAliasPlugin: import("bun").BunPlugin = {
  name: "path-alias",
  setup(build) {
    build.onResolve({ filter: /^@\// }, async (args) => {
      const basePath = args.path.replace(/^@\//, join(SRC_DIR, "/"));

      // Try exact path first
      const exactFile = Bun.file(basePath + ".ts");
      if (await exactFile.exists()) {
        return { path: basePath + ".ts" };
      }

      const exactTsxFile = Bun.file(basePath + ".tsx");
      if (await exactTsxFile.exists()) {
        return { path: basePath + ".tsx" };
      }

      // Try directory index
      const indexTs = Bun.file(join(basePath, "index.ts"));
      if (await indexTs.exists()) {
        return { path: join(basePath, "index.ts") };
      }

      const indexTsx = Bun.file(join(basePath, "index.tsx"));
      if (await indexTsx.exists()) {
        return { path: join(basePath, "index.tsx") };
      }

      // Fallback to original path
      return { path: basePath };
    });
  },
};

// Bundle the app
async function bundle() {
  const start = performance.now();
  const result = await Bun.build({
    entrypoints: [join(SRC_DIR, "main.tsx")],
    outdir: OUT_DIR,
    target: "browser",
    format: "esm",
    splitting: true,
    sourcemap: "external",
    minify: false,
    naming: "[name]-[hash].[ext]",
    plugins: [pathAliasPlugin],
    define: {
      "process.env.NODE_ENV": JSON.stringify("development"),
    },
  });

  if (!result.success) {
    console.error("Build failed:");
    for (const log of result.logs) {
      console.error(log);
    }
    return null;
  }

  const elapsed = (performance.now() - start).toFixed(0);
  console.log(`\x1b[32m[bun]\x1b[0m Bundled in ${elapsed}ms`);
  return result;
}

// Get the main bundle entry
async function getMainBundle(): Promise<string | null> {
  const dir = join(ROOT_DIR, ".bun-dev");
  const glob = new Bun.Glob("main-*.js");
  for await (const file of glob.scan(dir)) {
    return file;
  }
  return null;
}

// Generate HTML with the bundled script
async function generateHtml(): Promise<string> {
  const mainBundle = await getMainBundle();
  if (!mainBundle) {
    return "<html><body>Bundle not found. Check console for errors.</body></html>";
  }

  return `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Sleep Scoring</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
    <link rel="stylesheet" href="/dist/index.css" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/dist/${mainBundle}"></script>
    <script>
      // Live reload client
      const ws = new WebSocket('ws://localhost:${PORT}/__livereload');
      ws.onmessage = (e) => {
        if (e.data === 'reload') {
          console.log('[bun] Reloading...');
          location.reload();
        }
      };
      ws.onclose = () => {
        console.log('[bun] Dev server disconnected. Attempting reconnect...');
        setTimeout(() => location.reload(), 1000);
      };
    </script>
  </body>
</html>`;
}

// Build Tailwind CSS (v4 uses @tailwindcss/cli)
async function buildCss() {
  const proc = Bun.spawn(
    ["bunx", "@tailwindcss/cli", "-i", join(SRC_DIR, "index.css"), "-o", join(ROOT_DIR, ".bun-dev", "index.css")],
    {
      cwd: ROOT_DIR,
      stdout: "inherit",
      stderr: "inherit",
    }
  );
  await proc.exited;
}

// Notify all clients to reload
function notifyReload() {
  for (const ws of clients) {
    ws.send("reload");
  }
}

// Watch for file changes
function startWatcher() {
  let debounceTimer: Timer | null = null;

  const rebuild = async () => {
    console.log("\x1b[33m[bun]\x1b[0m File changed, rebuilding...");
    await Promise.all([bundle(), buildCss()]);
    notifyReload();
  };

  watch(SRC_DIR, { recursive: true }, (_event, _filename) => {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(rebuild, 100);
  });

  console.log(`\x1b[34m[bun]\x1b[0m Watching for changes in src/`);
}

// Main server
async function startServer() {
  console.log(`\x1b[34m[bun]\x1b[0m Starting development server...`);

  // Initial build
  await Promise.all([bundle(), buildCss()]);

  // Start file watcher
  startWatcher();

  const server = Bun.serve({
    port: PORT,
    async fetch(req) {
      const url = new URL(req.url);
      const pathname = url.pathname;

      // WebSocket upgrade for live reload
      if (pathname === "/__livereload") {
        const upgraded = server.upgrade(req);
        if (!upgraded) {
          return new Response("WebSocket upgrade failed", { status: 400 });
        }
        return undefined as unknown as Response;
      }

      // Proxy API requests to backend
      if (pathname.startsWith("/api")) {
        const backendUrl = `${BACKEND_URL}${pathname}${url.search}`;
        try {
          const hasBody = req.method !== "GET" && req.method !== "HEAD";
          const backendRes = await fetch(backendUrl, {
            method: req.method,
            headers: req.headers,
            ...(hasBody ? { body: req.body ?? null } : {}),
          });
          return new Response(backendRes.body, {
            status: backendRes.status,
            headers: backendRes.headers,
          });
        } catch (error) {
          console.error(`\x1b[31m[bun]\x1b[0m Proxy error:`, error);
          return new Response(JSON.stringify({ detail: "Backend unavailable" }), {
            status: 502,
            headers: { "Content-Type": "application/json" },
          });
        }
      }

      // Serve bundled assets
      if (pathname.startsWith("/dist/")) {
        const filePath = join(ROOT_DIR, ".bun-dev", pathname.slice(6));
        const file = Bun.file(filePath);
        if (await file.exists()) {
          const contentType = pathname.endsWith(".js")
            ? "application/javascript"
            : pathname.endsWith(".css")
              ? "text/css"
              : pathname.endsWith(".map")
                ? "application/json"
                : "application/octet-stream";
          return new Response(file, {
            headers: { "Content-Type": contentType },
          });
        }
      }

      // Serve public files
      if (pathname !== "/") {
        const publicFile = Bun.file(join(PUBLIC_DIR, pathname));
        if (await publicFile.exists()) {
          return new Response(publicFile);
        }
      }

      // SPA fallback - serve index.html for all routes
      const html = await generateHtml();
      return new Response(html, {
        headers: { "Content-Type": "text/html" },
      });
    },

    websocket: {
      open(ws) {
        clients.add(ws);
      },
      close(ws) {
        clients.delete(ws);
      },
      message() {},
    },
  });

  console.log(`
  \x1b[32m[bun]\x1b[0m Dev server running at:

    \x1b[36mLocal:\x1b[0m   http://localhost:${PORT}/
    \x1b[36mBackend:\x1b[0m ${BACKEND_URL}

  \x1b[33mPress Ctrl+C to stop\x1b[0m
`);
}

startServer();
