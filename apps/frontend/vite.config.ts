import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Slice 0 deployable frontend skeleton.
// In local dev, /api and /tiles are proxied to the BFF/TiTiler so the app uses
// the same same-origin contract it will use behind the Caddy gateway.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/tiles': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
});
