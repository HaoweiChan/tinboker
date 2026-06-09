import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'
import react from '@vitejs/plugin-react'
import path from 'path'


// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      // 'prompt': when a new deploy is detected we surface a styled toast
      // (PWAUpdatePrompt) whose 更新 button calls updateServiceWorker(true) → posts
      // SKIP_WAITING → the new SW activates → controllerchange reloads the page.
      // skipWaiting/clientsClaim are intentionally OFF so the waiting SW activates
      // only when the user taps 更新 (the button is the control). The earlier broken
      // prompt never posted SKIP_WAITING, so its button did nothing; this flow does.
      registerType: 'prompt',
      includeAssets: ['favicon.png', 'robots.txt', 'sitemap.xml'],
      manifest: {
        name: 'TinBoker - 聽播客',
        short_name: '聽播客',
        description: '結合 Podcast 觀點與即時數據的財經平台',
        theme_color: '#0e1014',
        background_color: '#0f1117',
        display: 'standalone',
        orientation: 'portrait-primary',
        start_url: '/',
        scope: '/',
        lang: 'zh-TW',
        categories: ['finance', 'business', 'news'],
        icons: [
          { src: '/icons/pwa/icon-72x72.png', sizes: '72x72', type: 'image/png' },
          { src: '/icons/pwa/icon-96x96.png', sizes: '96x96', type: 'image/png' },
          { src: '/icons/pwa/icon-128x128.png', sizes: '128x128', type: 'image/png' },
          { src: '/icons/pwa/icon-144x144.png', sizes: '144x144', type: 'image/png' },
          { src: '/icons/pwa/icon-152x152.png', sizes: '152x152', type: 'image/png' },
          { src: '/icons/pwa/icon-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/pwa/icon-384x384.png', sizes: '384x384', type: 'image/png' },
          { src: '/icons/pwa/icon-512x512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icons/pwa/maskable-192x192.png', sizes: '192x192', type: 'image/png', purpose: 'maskable' },
          { src: '/icons/pwa/maskable-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' }
        ]
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        // Prompt flow: the new SW WAITS (skipWaiting off) until the user taps 更新,
        // which posts SKIP_WAITING. clientsClaim MUST be on so the freshly-activated
        // worker claims this page → `controllerchange` fires → we reload. With it off,
        // skipWaiting activated the worker but never took control, so the button did
        // nothing visible.
        skipWaiting: false,
        clientsClaim: true,
        cleanupOutdatedCaches: true,
        maximumFileSizeToCacheInBytes: 6 * 1024 * 1024, // 6 MB to handle large bundles
        runtimeCaching: [
          {
            urlPattern: /^https:\/\/api\.tinboker\.com\/.*$/i,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache-v3', // Increment cache version to invalidate old cached data
              networkTimeoutSeconds: 30, // Increased from 10s to handle slower API calls
              cacheableResponse: { statuses: [200] }, // Only cache successful responses
              expiration: { maxEntries: 50, maxAgeSeconds: 60 * 5 } // 5 min cache for fresher data
            }
          },
          {
            urlPattern: /^https:\/\/fonts\.googleapis\.com\/.*/i,
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'google-fonts-stylesheets-v1',
              cacheableResponse: { statuses: [0, 200] }
            }
          },
          {
            urlPattern: /^https:\/\/fonts\.gstatic\.com\/.*/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'google-fonts-webfonts-v1',
              cacheableResponse: { statuses: [0, 200] },
              expiration: { maxEntries: 30, maxAgeSeconds: 60 * 60 * 24 * 365 }
            }
          },
          {
            urlPattern: /\.(?:png|jpg|jpeg|svg|gif|webp)$/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'images-cache-v1',
              cacheableResponse: { statuses: [0, 200] },
              expiration: { maxEntries: 100, maxAgeSeconds: 60 * 60 * 24 * 30 }
            }
          }
        ]
      },
      devOptions: {
        enabled: false
      }
    })
  ],
  // App version (from package.json) exposed to the client for the sidebar version label.
  define: {
    __APP_VERSION__: JSON.stringify(process.env.npm_package_version ?? '0.0.0'),
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:5174',
        changeOrigin: true,
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  optimizeDeps: {
    include: ['technicalindicators'],
    esbuildOptions: {
      target: 'esnext',
    },
  },
  build: {
    commonjsOptions: {
      include: [/technicalindicators/, /node_modules/],
    },
  },
})
