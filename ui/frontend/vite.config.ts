/**
 * Vite configuration for Arthayukti React UI
 * 
 * This project builds the React SPA for the Arthayukti HFT Dashboard.
 * Build output directory is ../static-react, which is used by FastAPI in ui/dashboard.py.
 * The build creates:
 *   - ui/static-react/index.html (entry point)
 *   - ui/static-react/assets/*.js (JavaScript bundles)
 *   - ui/static-react/assets/*.css (CSS bundles)
 */
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../static-react',
    emptyOutDir: true,
  },
  base: '/',  // Ensures assets are served as /assets/... from root
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:9000',
        changeOrigin: true,
      },
    },
  },
})
