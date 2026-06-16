import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  // `react()` is typed against the root `vite` install, while `vitest` bundles its
  // own nested `vite` whose `PluginOption` type is structurally identical but
  // nominally different. Cast to avoid the duplicate-vite type clash.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  plugins: [react() as any],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    css: false,
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    // Some route/page tests render the full app shell and chain multiple
    // `waitFor` calls (up to 8000ms each, sometimes several per test), which
    // exceeds Vitest's 5000ms default and causes flaky timeouts in CI.
    testTimeout: 30000,
    hookTimeout: 30000,
  },
});