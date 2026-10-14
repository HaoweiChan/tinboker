import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'
import react from '@vitejs/plugin-react'
import path from 'path'

// One installable app per origin (scope "/"), so on dev and staging the site and the
// back office (/admin) are the same home-screen app. Non-production builds get a
// stage-labelled name and the gear icons (scripts/make-admin-icons.py) so the tile
// can't be mistaken for the production app. VITE_STAGE comes from CI; unset (a bare
// local build) counts as non-production, same as App.tsx's ADMIN_ENABLED.
const STAGE = process.env.VITE_STAGE
const IS_PROD = STAGE === 'PRODUCTION'
const APP_TITLE = IS_PROD ? '聽播客' : `聽播客 ${STAGE === 'STAGING' ? 'Staging' : STAGE === 'DEV' ? 'Dev' : 'Local'}`
const ICON_DIR = IS_PROD ? '/icons/pwa' : '/icons/pwa/admin'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    {
      // iOS ignores the manifest and reads these tags off the page being added.
      name: 'pwa-stage-html',
      transformIndexHtml: (html: string) => html
        .replace('name="apple-mobile-web-app-title" content="聽播客"', `name="apple-mobile-web-app-title" content="${APP_TITLE}"`)
        .replace('href="/icons/pwa/apple-touch-icon.png"', `href="${ICON_DIR}/apple-touch-icon.png"`),
    },
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
        id: '/',
        name: IS_PROD ? 'TinBoker - 聽播客' : `TinBoker - ${APP_TITLE}`,
        short_name: APP_TITLE,
        description: '結合 Podcast 觀點與即時數據的財經平台',
        theme_color: '#0e1014',
        background_color: '#0f1117',
        display: 'standalone',
        orientation: 'portrait-primary',
        start_url: '/',
        scope: '/',
        lang: 'zh-TW',
        categories: ['finance', 'business', 'news'],
        icons: [72, 96, 128, 144, 152, 192, 384, 512].map((n) => ({
          src: `${ICON_DIR}/icon-${n}x${n}.png`, sizes: `${n}x${n}`, type: 'image/png'
        })).concat([192, 512].map((n) => ({
          src: `${ICON_DIR}/maskable-${n}x${n}.png`, sizes: `${n}x${n}`, type: 'image/png',
          purpose: 'maskable' as const
        })))
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
  // App version label shown in the sidebar. CI passes VITE_RELEASE_VERSION already
  // formatted per env: "v0.4.8" on tagged prod, "staging-<sha>" / "dev-<sha>" on branch
  // builds — used verbatim. Falls back to package.json for local builds.
  define: {
    __APP_VERSION__: JSON.stringify(
      process.env.VITE_RELEASE_VERSION ||
      process.env.npm_package_version ||
      '0.0.0',
    ),
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
