// Vite config of the U1 gate build: one IIFE file and one CSS file for the specimen snapshot.
// Run from the repo root: node frontend/node_modules/vite/bin/vite.js build --config .scratch/dev-center-build/gates/u1/specimen.vite.config.mjs
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
    outDir: process.env.U1_GATE_OUT || here("./build"),
    emptyOutDir: true,
    cssCodeSplit: false,
    lib: { entry: here("./specimen-entry.js"), formats: ["iife"], name: "PbiSpecimen", fileName: () => "specimen.js" },
    rollupOptions: { output: { inlineDynamicImports: true, assetFileNames: "specimen[extname]" } },
  },
};
