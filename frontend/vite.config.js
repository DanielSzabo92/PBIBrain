import { defineConfig, loadEnv } from "vite";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import { devcenterFakeEnabled, devcenterFakePlugin, devcenterFakeProxy } from "./vite-plugins/devcenterFake.js";

export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, process.cwd(), ""), ...process.env };
  const fake = devcenterFakeEnabled(env);
  return {
    plugins: [tailwindcss(), devcenterFakePlugin({ enabled: fake })],
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
