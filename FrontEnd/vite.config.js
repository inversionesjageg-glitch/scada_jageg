import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: [
        'app.grupopolytex.com',
        '190.6.54.13'
    ],
    host: true,
    port: 3001
  }
});