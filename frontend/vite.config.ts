import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ command, mode }) => {
  if (command === 'build') {
    const env = loadEnv(mode, process.cwd(), 'VITE_');
    const value = (process.env.VITE_API_BASE_URL ?? env.VITE_API_BASE_URL ?? '').trim();
    let valid = false;
    try {
      const url = new URL(value);
      valid = url.protocol === 'https:' && !url.username && !url.password
        && !url.search && !url.hash && (url.pathname === '/' || url.pathname === '')
        && !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
    } catch { /* Report configuration names only, never environment contents. */ }
    if (!valid) throw new Error('Set VITE_API_BASE_URL to the HTTPS backend origin before building.');
  }
  return { plugins: [react()] };
})
