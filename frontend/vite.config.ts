import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The API runs separately (uvicorn on :8000); the dev server proxies /api to it.
export default defineConfig({
  plugins: [react()],
  // Monaco (the code editor) is large but lazy-loaded only on coding screens.
  build: { chunkSizeWarningLimit: 2500 },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
