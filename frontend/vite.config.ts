import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 빌드 결과를 백엔드가 그대로 제공한다. 개발 서버에서는 API를 8000번 포트로 넘긴다.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "../backend/app/static", emptyOutDir: true, chunkSizeWarningLimit: 1200 },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
