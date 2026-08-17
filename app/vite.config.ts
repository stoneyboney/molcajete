import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

// Served from https://<user>.github.io/molcajete/ — a project page, so every
// asset URL needs the sub-path. `start_url` and `scope` below must agree with
// it or iOS launches the home-screen icon into a fresh browser context.
const BASE = '/molcajete/'

export default defineConfig({
  base: BASE,
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      // No `includeAssets`: the icons live in public/ and the glob below
      // already precaches them. Listing them twice puts duplicate entries in
      // the precache manifest.
      manifest: {
        name: 'Molcajete',
        short_name: 'Molcajete',
        description: 'Spanisch lesen, mit vorbereitetem Wortschatz.',
        lang: 'de',
        start_url: BASE,
        scope: BASE,
        display: 'standalone',
        orientation: 'portrait',
        background_color: '#fbf7f0',
        theme_color: '#fbf7f0',
        icons: [
          { src: 'icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          {
            src: 'icons/icon-512-maskable.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        // The app shell, and nothing else. Bundles live in IndexedDB; caching
        // them here would duplicate megabytes and give the cache a second,
        // silently diverging copy of the contract. There are deliberately no
        // runtimeCaching rules — CLAUDE.md constraint 1 means there is no
        // runtime request to cache.
        globPatterns: ['**/*.{js,css,html,png,svg,woff2}'],
        navigateFallback: `${BASE}index.html`,
        cleanupOutdatedCaches: true,
      },
      devOptions: { enabled: false },
    }),
  ],
})
