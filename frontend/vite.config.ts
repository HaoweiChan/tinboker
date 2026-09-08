import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'
import react from '@vitejs/plugin-react'
import path from 'path'

// dev and staging are built as their own bundles (VITE_STAGE, set per-ref in
// .github/workflows/frontend-deploy.yml) and both sit behind EnvGate, which walls the
// WHOLE site behind a Google login + admin check. There is no public surface there, so
// their manifest is the back office: installing dev.tinboker.com to a home screen gives
// you an app that opens on /admin, not on the public homepage. Same icons as the public
// app — the origin is different, so the two installs never collide.
const IS_ADMIN_BUILD = process.env.VITE_STAGE !== 'PRODUCTION'
// Same mark on the app's near-black ground — the treatment the maskable icons already
// use, applied full-bleed. Regenerate with scripts/make-admin-icons.py.
const ICONS = IS_ADMIN_BUILD ? '/icons/pwa/admin' : '/icons/pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    {
      // iOS reads this for the home-screen name, not the manifest.
      name: 'admin-build-html',
      transformIndexHtml: (html: string) => IS_ADMIN_BUILD
        ? html
            .replace('name="apple-mobile-web-app-title" content="聽播客"',
                     'name="apple-mobile-web-app-title" content="聽播客後台"')
            .replace('href="/icons/pwa/apple-touch-icon.png"',
                     'href="/icons/pwa/admin/apple-touch-icon.png"')
        : html,
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
        name: IS_ADMIN_BUILD ? 'TinBoker 後台' : 'TinBoker - 聽播客',
        short_name: IS_ADMIN_BUILD ? '聽播客後台' : '聽播客',
        description: IS_ADMIN_BUILD
          ? 'TinBoker 管理後台 — 留言、社群、內容、翻譯'
          : '結合 Podcast 觀點與即時數據的財經平台',
        theme_color: '#0e1014',
        background_color: '#0f1117',
        display: 'standalone',
        orientation: 'portrait-primary',
        // Opens on the back office; scope stays '/' so every route still runs in-app.
        start_url: IS_ADMIN_BUILD ? '/admin' : '/',
        scope: '/',
        lang: 'zh-TW',
        categories: IS_ADMIN_BUILD ? ['productivity'] : ['finance', 'business', 'news'],
        icons: [72, 96, 128, 144, 152, 192, 384, 512].map((n) => ({
          src: `${ICONS}/icon-${n}x${n}.png`, sizes: `${n}x${n}`, type: 'image/png'
        })).concat([192, 512].map((n) => ({
          src: `${ICONS}/maskable-${n}x${n}.png`, sizes: `${n}x${n}`, type: 'image/png',
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
