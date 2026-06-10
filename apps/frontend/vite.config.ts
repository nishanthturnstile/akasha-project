import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import fs from 'node:fs';
import path from 'node:path';

// Akasha Vite frontend (Phase 4). In local dev /api and /tiles are proxied to the
// BFF gateway so the app uses the same same-origin contract it will use behind Caddy.
// The gateway host port comes from infra/docker/.env (WEB_PORT), with 8080 as
// the compose default. AKASHA_DEV_PROXY_TARGET remains an explicit override.
function dockerGatewayTarget(): string {
  const dockerEnvPath = path.resolve(__dirname, '../../infra/docker/.env');
  const fallbackPort = '8080';

  try {
    const envText = fs.readFileSync(dockerEnvPath, 'utf8');
    const webPort = envText
      .split(/\r?\n/)
      .map((line) => line.trim())
      .find((line) => line.startsWith('WEB_PORT='))
      ?.split('=')
      .slice(1)
      .join('=')
      .trim();
    return `http://localhost:${webPort || fallbackPort}`;
  } catch {
    return `http://localhost:${fallbackPort}`;
  }
}

const devProxyTarget = process.env.AKASHA_DEV_PROXY_TARGET ?? dockerGatewayTarget();

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
