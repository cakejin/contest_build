import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    // FastAPI(webapp/app.py)가 이 디렉터리를 그대로 정적 마운트한다 — 빌드 산출물이
    // 곧 서빙되는 파일이므로 outDir을 백엔드가 이미 참조 중인 경로에 맞춘다.
    outDir: '../static',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
