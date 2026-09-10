import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Vite dev-server config for the Variant Review UI.
//
// The app talks to the Clinical Genomics Insight Platform FastAPI service
// (see ../api/README.md), which defaults to http://127.0.0.1:8000 when run
// with `uvicorn api.main:app --reload`. Set VITE_API_BASE_URL to point at a
// different host; otherwise requests to /api/* are proxied to the local API
// during `npm run dev` so the browser never needs CORS configuration.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiBase = env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

  return {
    plugins: [react()],
    server: {
      proxy: {
        "/api": {
          target: apiBase,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
      },
    },
  };
});
