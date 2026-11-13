import { defineConfig, loadEnv } from "vite";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import { devcenterFakeEnabled, devcenterFakePlugin, devcenterFakeProxy } from "./vite-plugins/devcenterFake.js";

export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, process.cwd(), ""), ...process.env };
  const fake = devcenterFakeEnabled(env);
  return {
    plugins: [tailwindcss(), devcenterFakePlugin({ enabled: fake })],
    build: {
      rollupOptions: {
        output: {
          // Libraries change far less often than the app: separate files stay cached across releases.
          manualChunks(id) {
            if (!id.includes("node_modules")) return undefined;
            if (/node_modules\/(react|react-dom|scheduler)\//.test(id)) return "react";
            if (/node_modules\/(@xyflow|@dagrejs|dagre|d3-[^/]+)\//.test(id)) return "graph";
            if (/node_modules\/(@radix-ui|radix-ui|@floating-ui)\//.test(id)) return "radix";
            if (id.includes("node_modules/lucide-react/")) return "icons";
            return undefined;
          },
        },
      },
    },
    resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
    server: {
      host: "127.0.0.1",
      port: 5173,
      proxy: fake
        ? devcenterFakeProxy(env)
        : {
            "/api": {
              target: env.BRAIN_API_URL || "http://127.0.0.1:8000",
              changeOrigin: true,
            },
          },
    },
  };
});
