import { useCallback, useEffect, useState } from 'react'
import { useRegisterSW } from 'virtual:pwa-register/react'
import { ArrowUpCircle, X } from 'lucide-react'

const PWA_UPDATE_KEY = 'pwa-update-reload'
const SUPPRESS_MS = 10_000
const RELOAD_BACKSTOP_MS = 2_500
const VISIBILITY_CHECK_MIN_INTERVAL_MS = 5 * 60 * 1000

// Module-level once-guard: controllerchange, the waiting worker's statechange
// and the backstop timer can all race to reload — only the first one navigates.
// Reset after a few seconds so a (theoretical) failed navigation can be retried.
let reloading = false

function forceReload() {
  if (reloading) return
  reloading = true
  setTimeout(() => { reloading = false }, RELOAD_BACKSTOP_MS + 2_000)
  sessionStorage.setItem(PWA_UPDATE_KEY, String(Date.now()))
  // location.replace + cache-bust param: iOS standalone PWAs swallow
  // location.reload(), and replace() keeps ?_t URLs out of the history stack.
  const url = new URL(window.location.href)
  url.searchParams.set('_t', String(Date.now()))
  window.location.replace(url.toString())
}

/**
 * PWA update prompt (registerType: 'prompt').
 *
 * When a new service worker reaches the waiting state we surface a toast.
 * Tapping 立即更新 posts SKIP_WAITING directly to the waiting worker → it
 * activates → controllerchange → force-reload into the new build.
 *
 * Hard-won rules encoded here (see PRs #62 #96 #110):
 * - Arm the reload backstop BEFORE any async work. Awaiting reg.update() (a
 *   network fetch of sw.js) before scheduling it left 更新中… hanging forever
 *   on slow mobile connections.
 * - Never call reg.update() in the click path at all — update checks belong in
 *   the background, not between the user's tap and the reload.
 * - If needRefresh is set but no waiting worker exists (page was frozen on iOS,
 *   another tab activated it, …) there is nothing to message: just reload.
 * - location.reload() is swallowed by iOS standalone PWAs; always navigate via
 *   location.replace() with a cache-bust param.
 */
export function PWAUpdatePrompt() {
  const {
    needRefresh: [needRefresh, setNeedRefresh],
  } = useRegisterSW({
    immediate: true,
    onRegisteredSW(_swUrl, r) {
      if (import.meta.env.DEV) console.log('[PWA] service worker registered')
      if (!r) return
      // Hourly poll for long-open tabs, plus a rate-limited check whenever the
      // app is foregrounded — iOS freezes timers in the background, so
      // visibilitychange is the reliable "user came back" signal.
      let lastCheck = Date.now()
      const check = () => {
        lastCheck = Date.now()
        r.update().catch(() => {})
      }
      setInterval(check, 60 * 60 * 1000)
      document.addEventListener('visibilitychange', () => {
        if (
          document.visibilityState === 'visible' &&
          Date.now() - lastCheck > VISIBILITY_CHECK_MIN_INTERVAL_MS
        ) check()
      })
    },
    onRegisterError(error) {
      console.error('[PWA] service worker registration error:', error)
    },
  })

  const [updating, setUpdating] = useState(false)
  const [suppressed, setSuppressed] = useState(() => {
    const ts = sessionStorage.getItem(PWA_UPDATE_KEY)
    if (ts && Date.now() - Number(ts) < SUPPRESS_MS) return true
    sessionStorage.removeItem(PWA_UPDATE_KEY)
    return false
  })

  useEffect(() => {
    if (!suppressed) return
    const id = setTimeout(() => {
      sessionStorage.removeItem(PWA_UPDATE_KEY)
      setSuppressed(false)
    }, SUPPRESS_MS)
    return () => clearTimeout(id)
  }, [suppressed])

  useEffect(() => {
    if (!('serviceWorker' in navigator)) return
    // clientsClaim fires controllerchange on the FIRST install too (null → SW).
    // Only an update (existing controller replaced) should trigger a reload —
    // otherwise every brand-new visitor gets force-reloaded seconds after landing.
    let hadController = !!navigator.serviceWorker.controller
    const handler = () => {
      if (!hadController) {
        hadController = true
        return
      }
      forceReload()
    }
    navigator.serviceWorker.addEventListener('controllerchange', handler)
    return () => navigator.serviceWorker.removeEventListener('controllerchange', handler)
  }, [])

  // Strip the ?_t cache-bust param after a forced reload so it doesn't pile up
  // or leak into shared/bookmarked URLs.
  useEffect(() => {
    const url = new URL(window.location.href)
    if (url.searchParams.has('_t')) {
      url.searchParams.delete('_t')
      window.history.replaceState(window.history.state, '', url.pathname + url.search + url.hash)
    }
  }, [])

  const handleUpdate = useCallback(() => {
    if (updating) return
    setUpdating(true)

    // Absolute backstop, armed synchronously: whatever happens below, the page
    // navigates within RELOAD_BACKSTOP_MS — the button can never dead-end.
    setTimeout(forceReload, RELOAD_BACKSTOP_MS)

    if (!('serviceWorker' in navigator)) {
      forceReload()
      return
    }

    navigator.serviceWorker.getRegistration()
      .then((reg) => {
        const waiting = reg?.waiting
        if (!waiting) {
          // Stale prompt — no installed update to switch to; reload picks up
          // whatever is current.
          forceReload()
          return
        }
        waiting.addEventListener('statechange', () => {
          if (waiting.state === 'activated') forceReload()
        })
        // The generated sw.js handles this message with self.skipWaiting();
        // activation fires controllerchange (listener above) → reload.
        waiting.postMessage({ type: 'SKIP_WAITING' })
      })
      .catch(() => forceReload())
  }, [updating])

  if (!needRefresh || suppressed) return null

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-20 right-4 left-4 sm:left-auto sm:bottom-4 z-[60] sm:max-w-[340px] animate-in fade-in slide-in-from-bottom-2 duration-200"
    >
      <div className="flex items-start gap-3 rounded-[var(--radius-md)] border border-border bg-card/95 backdrop-blur p-3.5 shadow-lg shadow-black/30">
        <div className="grid place-items-center h-8 w-8 shrink-0 rounded-full bg-accent-info-soft text-accent-info">
          <ArrowUpCircle size={18} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-semibold text-foreground">有新版本可用</div>
          <p className="mt-0.5 text-[12px] leading-[1.5] text-muted-foreground">
            重新整理以載入最新內容與修正。
          </p>
          <div className="mt-2.5 flex items-center gap-2">
            <button
              type="button"
              onClick={handleUpdate}
              disabled={updating}
              className="inline-flex items-center justify-center rounded-md bg-accent-info px-3 py-1.5 text-[12px] font-semibold text-accent-info-foreground hover:opacity-90 transition-opacity disabled:opacity-60"
            >
              {updating ? '更新中…' : '立即更新'}
            </button>
            <button
              type="button"
              onClick={() => setNeedRefresh(false)}
              className="inline-flex items-center justify-center rounded-md px-2.5 py-1.5 text-[12px] font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            >
              稍後
            </button>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setNeedRefresh(false)}
          aria-label="關閉"
          className="grid place-items-center h-6 w-6 shrink-0 rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  )
}
