import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// SYNC-INFRA-001 3·4장 — React 빌드 결과는 FastAPI가 `/`에서 서빙(syncdoc/web/static). 개발 중엔 :8000으로 프록시.
export default defineConfig({
  plugins: [react()],
  build: { outDir: '../syncdoc/web/static', emptyOutDir: true },
  server: {
    proxy: { '/api': 'http://localhost:8000', '/auth': 'http://localhost:8000', '/mcp': 'http://localhost:8000' },
  },
})
