import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// The API base defaults to the local backend; override with VITE_API_BASE for the droplet
// (e.g. VITE_API_BASE=https://your-domain/trading).
export default defineConfig({
  plugins: [svelte()],
  // Where the built page is served from (e.g. /wizard/ behind nginx). Default: the site root.
  base: process.env.VITE_BASE || '/',
  server: { port: 5173 },
})
