import { defineConfig } from "vite";

export default defineConfig({
  base: "/app/",
  esbuild: { jsx: "automatic" },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    assetsDir: "assets",
    sourcemap: false,
    // EXE-01 bundle budget reads the import graph from this manifest instead of
    // guessing which chunks a route pulls in.
    manifest: true,
    rollupOptions: {
      output: {
        entryFileNames: "assets/index.js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "assets/[name][extname]"
      }
    }
  }
});
