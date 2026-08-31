import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    server: {
      host: "127.0.0.1",
      port: 5173,
      proxy: {
        "/api": {
          target: env.BRAIN_API_URL || "http://127.0.0.1:8000",
          changeOrigin: true,
        },
      },
    },
  };
});
