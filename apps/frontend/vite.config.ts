import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'node:path';

// Akasha Vite frontend (Phase 4). In local dev /api and /tiles are proxied to the
// BFF gateway so the app uses the same same-origin contract it will use behind Caddy.
// In the Emergent preview, ingress routes /api/* to the BFF directly (port 8001).
const devProxyTarget = process.env.AKASHA_DEV_PROXY_TARGET ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': { target: devProxyTarget, changeOrigin: true },
      '/tiles': { target: devProxyTarget, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
});
