import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发服务器把 /api 请求代理到后端 FastAPI（127.0.0.1:8001）
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
      },
    },
  },
});
