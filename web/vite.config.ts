import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/forge/intake': 'http://localhost:8000',
      '/forge/generate-scenario': 'http://localhost:8000',
      '/simulations': 'http://localhost:8000',
      '/api': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
