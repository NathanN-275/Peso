import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

const backendProxyPath = '/__peso_api';
const backendProxyTarget = process.env.VITE_BACKEND_PROXY_TARGET || 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      [backendProxyPath]: {
        target: backendProxyTarget,
        changeOrigin: true,
        rewrite: (path) => path.slice(backendProxyPath.length) || '/',
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/testSetup.ts',
  },
});
