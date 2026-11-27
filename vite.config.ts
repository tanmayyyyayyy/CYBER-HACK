import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const frontendPort = Number(process.env.DRISHTI_FRONTEND_PORT || 5174);
const backendPort = Number(process.env.DRISHTI_BACKEND_PORT || 8000);
const portalPort = Number(process.env.DRISHTI_PORTAL_PORT || 8100);

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: frontendPort,
    strictPort: true,
    watch: {
      ignored: ['**/backend/**', '**/security_portal/**', '**/models/**', '**/demo_feeds/**', '**/.venv/**', '**/dist/**', '**/scripts/**'],
    },
    headers: {
      'Content-Security-Policy': `default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self' ws://127.0.0.1:${frontendPort}; font-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'`,
      'X-Content-Type-Options': 'nosniff',
      'X-Frame-Options': 'DENY',
      'Referrer-Policy': 'no-referrer',
      'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
      'Cross-Origin-Resource-Policy': 'same-origin',
    },
    proxy: {
      '/api': `http://127.0.0.1:${backendPort}`,
      '/sec-api': `http://127.0.0.1:${portalPort}`,
    },
  },
  preview: { host: '127.0.0.1', port: 4174, strictPort: true },
});
