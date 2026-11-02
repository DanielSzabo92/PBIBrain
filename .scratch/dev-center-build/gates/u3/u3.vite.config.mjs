// Vite config of the U3 gate build: one IIFE file and one CSS file for the screen snapshots.
// Run from the repo root: node frontend/node_modules/vite/bin/vite.js build --config .scratch/dev-center-build/gates/u3/u3.vite.config.mjs
import { fileURLToPath, pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const here = (path) => fileURLToPath(new URL(path, import.meta.url));
const require = createRequire(here("../../../../frontend/package.json"));
const tailwindcss = (await import(pathToFileURL(require.resolve("@tailwindcss/vite")).href)).default;

export default {
  root: here("../../../../frontend"),
  plugins: [tailwindcss()],
  resolve: { alias: { "@": here("../../../../frontend/src") } },
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
  build: {
    outDir: process.env.U3_GATE_OUT || here("./build"),
    emptyOutDir: true,
    cssCodeSplit: false,
    lib: { entry: here("./u3-entry.jsx"), formats: ["iife"], name: "PbiU3", fileName: () => "u3.js" },
    rollupOptions: { output: { inlineDynamicImports: true, assetFileNames: "u3[extname]" } },
  },
};
