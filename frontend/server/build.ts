/**
 * Bun production build script
 */

import { rm, mkdir, copyFile } from "fs/promises";
import { join, resolve } from "path";

const ROOT_DIR = resolve(import.meta.dir, "..");
const SRC_DIR = join(ROOT_DIR, "src");
const DIST_DIR = join(ROOT_DIR, "dist");
const PUBLIC_DIR = join(ROOT_DIR, "public");

// Path alias plugin for @/ -> src/
const pathAliasPlugin: import("bun").BunPlugin = {
  name: "path-alias",
  setup(build) {
    build.onResolve({ filter: /^@\// }, async (args) => {
      const relativePath = args.path.replace(/^@\//, "");
      const basePath = join(SRC_DIR, relativePath);

      // Try different extensions
      const extensions = [".tsx", ".ts", ".js", ".jsx", ""];
      for (const ext of extensions) {
        const fullPath = basePath + ext;
        const file = Bun.file(fullPath);
        if (await file.exists()) {
          return { path: fullPath };
        }
      }

      // Try as directory with index file
      const indexExtensions = [".tsx", ".ts", ".js", ".jsx"];
      for (const ext of indexExtensions) {
        const indexPath = join(basePath, "index" + ext);
        const file = Bun.file(indexPath);
        if (await file.exists()) {
          return { path: indexPath };
        }
      }

      // Fallback to original behavior
      return { path: basePath };
    });
  },
};

async function build() {
  console.log("\x1b[34m[build]\x1b[0m Starting production build...\n");
  const startTime = performance.now();

  // Clean dist directory
  await rm(DIST_DIR, { recursive: true, force: true });
  await mkdir(DIST_DIR, { recursive: true });
  await mkdir(join(DIST_DIR, "assets"), { recursive: true });

  // Bundle JavaScript
  console.log("\x1b[33m[build]\x1b[0m Bundling JavaScript...");
  const result = await Bun.build({
    entrypoints: [join(SRC_DIR, "main.tsx")],
    outdir: join(DIST_DIR, "assets"),
    target: "browser",
    format: "esm",
    splitting: true,
    sourcemap: "external",
    minify: true,
    naming: "[name]-[hash].[ext]",
    plugins: [pathAliasPlugin],
    define: {
      "process.env.NODE_ENV": JSON.stringify("production"),
    },
  });

  if (!result.success) {
    console.error("\x1b[31m[build]\x1b[0m Build failed:");
    for (const log of result.logs) {
      console.error(log);
    }
    process.exit(1);
  }

  // Get the main bundle filenames (JS and CSS extracted from JS imports like uPlot)
  // Use path.basename for cross-platform support (Windows backslashes vs Linux forward slashes)
  let mainBundle = "";
  let mainCssBundle = "";
  for (const output of result.outputs) {
    const name = output.path.replace(/\\/g, "/").split("/").pop() || "";
    if (name.startsWith("main-") && name.endsWith(".js")) {
      mainBundle = name;
    }
    if (name.startsWith("main-") && name.endsWith(".css")) {
      mainCssBundle = name;
    }
    console.log("  \x1b[32m✓\x1b[0m " + name + " (" + (output.size / 1024).toFixed(1) + " KB)");
  }

  // Build Tailwind CSS
  console.log("\n\x1b[33m[build]\x1b[0m Building CSS...");
  const cssProc = Bun.spawn(
    [
      "bunx",
      "tailwindcss",
      "-i",
      join(SRC_DIR, "index.css"),
      "-o",
      join(DIST_DIR, "assets", "index.css"),
      "--minify",
    ],
    {
      cwd: ROOT_DIR,
      stdout: "inherit",
      stderr: "inherit",
    }
  );
  await cssProc.exited;

  // Copy public files
  console.log("\n\x1b[33m[build]\x1b[0m Copying public files...");
  const publicGlob = new Bun.Glob("**/*");
  for await (const file of publicGlob.scan(PUBLIC_DIR)) {
    const src = join(PUBLIC_DIR, file);
    const dest = join(DIST_DIR, file);
    await mkdir(join(DIST_DIR, file, ".."), { recursive: true });
    await copyFile(src, dest);
    console.log("  \x1b[32m✓\x1b[0m " + file);
  }

  // Generate index.html
  // Use absolute paths (/assets/) so SPA client-side routing works on nested routes
  // docker-entrypoint.sh injects <base href> when BASE_PATH is set for sub-path deployments
  console.log("\n\x1b[33m[build]\x1b[0m Generating index.html...");
  const html = `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Sleep Scoring</title>
    <link rel="stylesheet" href="/assets/index.css" />${mainCssBundle ? `\n    <link rel="stylesheet" href="/assets/${mainCssBundle}" />` : ""}
  </head>
  <body>
    <div id="root"></div>
    <script src="/config.js"></script>
    <script type="module" src="/assets/${mainBundle}"></script>
  </body>
</html>`;

  await Bun.write(join(DIST_DIR, "index.html"), html);

  const elapsed = ((performance.now() - startTime) / 1000).toFixed(2);
  console.log("\n\x1b[32m[build]\x1b[0m Build completed in " + elapsed + "s");
  console.log("\x1b[32m[build]\x1b[0m Output: " + DIST_DIR);
}

build();
