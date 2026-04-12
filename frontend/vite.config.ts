import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/parser2/',
  server: {
    port: 3000,
    proxy: {
      '/parser2/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/parser2/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  },
})
