// Vite config for the U7 gate build: one IIFE file and one CSS file for the screen snapshots.
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
    outDir: process.env.U7_GATE_OUT || here("./build"),
    emptyOutDir: true,
    cssCodeSplit: false,
    lib: { entry: here("./u7-entry.jsx"), formats: ["iife"], name: "PbiU7", fileName: () => "u7.js" },
    rollupOptions: { output: { inlineDynamicImports: true, assetFileNames: "u7[extname]" } },
  },
};
