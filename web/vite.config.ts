import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// The API base defaults to the local backend; override with VITE_API_BASE for the droplet
// (e.g. VITE_API_BASE=https://your-domain/trading).
export default defineConfig({
  plugins: [svelte()],
  server: { port: 5173 },
})
