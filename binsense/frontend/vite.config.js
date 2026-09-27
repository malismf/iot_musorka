import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// В режиме разработки (npm run dev) запросы к /api уходят на локальный backend.
// В продакшене фронтенд и API обслуживает один домен через Caddy — прокси не нужен.
const API = process.env.VITE_API_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: API, changeOrigin: true, ws: true },
    },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1200,
  },
})
