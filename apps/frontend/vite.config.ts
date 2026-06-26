import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import fs from 'node:fs';
import path from 'node:path';

// Akasha Vite frontend (Phase 4). In local dev /api and /tiles are proxied to the
// BFF gateway so the app uses the same same-origin contract it will use behind Caddy.
// The gateway host port comes from infra/docker/.env (WEB_PORT), with 8080 as
// the compose default. AKASHA_DEV_PROXY_TARGET remains an explicit override.
function readDockerEnvValue(key: string): string | undefined {
  const dockerEnvPath = path.resolve(__dirname, '../../infra/docker/.env');

  try {
    const envText = fs.readFileSync(dockerEnvPath, 'utf8');
    return envText
      .split(/\r?\n/)
      .map((line) => line.trim())
      .find((line) => line.startsWith(`${key}=`))
      ?.split('=')
      .slice(1)
      .join('=')
      .trim();
  } catch {
    return undefined;
  }
}

function dockerGatewayTarget(): string {
  return `http://localhost:${readDockerEnvValue('WEB_PORT') || '8080'}`;
}

function frontendPort(): number {
  const rawPort = readDockerEnvValue('FRONTEND_PORT') || '5173';
  const parsedPort = Number(rawPort);
  return Number.isInteger(parsedPort) && parsedPort > 0 ? parsedPort : 5173;
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
    port: frontendPort(),
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
