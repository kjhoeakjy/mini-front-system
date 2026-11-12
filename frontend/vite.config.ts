import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 기본 빌드: 백엔드가 제공하는 backend/app/static. pages 모드: 정적 배포용 site/ (상대 경로).
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: mode === "pages" ? "./" : "/",
  build: { outDir: mode === "pages" ? "../site" : "../backend/app/static", emptyOutDir: true, chunkSizeWarningLimit: 1200 },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
}));
