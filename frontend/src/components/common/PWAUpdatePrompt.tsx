import { useCallback, useEffect, useState } from 'react'
import { useRegisterSW } from 'virtual:pwa-register/react'
import { ArrowUpCircle, X } from 'lucide-react'
import { usePlayerStore } from '@/store/usePlayerStore'

const PWA_UPDATE_KEY = 'pwa-update-reload'
const SUPPRESS_MS = 10_000
// Anti-hang fallback only — NOT the normal reload path. The reload is driven by
// `controllerchange` (the new worker actually taking control); this timer just
// guarantees the 更新中… button can't dead-end if a worker never takes control
// (errored, or nothing was really pending). Long enough not to race a slow
// mobile install+activate — a shorter value reloaded into the still-active OLD
// worker, re-serving the stale build and looping the prompt (the bug this fixes).
const RELOAD_BACKSTOP_MS = 10_000
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
 * - Reload ONLY on `controllerchange` — i.e. once the new worker actually
 *   controls this page. Reloading any sooner re-serves the old build from the
 *   still-active old worker, which re-arms needRefresh and loops the prompt
 *   ("clicked 更新, still old version, prompt again" until the SW finally claims).
 * - The click-path timer is a long anti-hang BACKSTOP, never the normal path.
 *   A short blind reload raced the SW activation and won on slow mobile, causing
 *   exactly that loop.
 * - Never call reg.update() in the click path — update checks belong in the
 *   background, not between the user's tap and the reload (awaiting that network
 *   fetch is what left 更新中… hanging forever).
 * - If needRefresh is set but no waiting/installing worker exists (page was
 *   frozen on iOS, another tab activated it, …) there is nothing to activate:
 *   just reload.
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

    if (!('serviceWorker' in navigator)) {
      forceReload()
      return
    }

    // The real reload is driven by `controllerchange` (the effect above), which
    // fires only once the new worker has actually claimed this page. This timer
    // is just an anti-hang backstop for the case where no worker ever takes
    // control — see RELOAD_BACKSTOP_MS. Armed synchronously so the button can't
    // dead-end even if getRegistration() never resolves.
    const backstop = setTimeout(forceReload, RELOAD_BACKSTOP_MS)

    // Tell the generated sw.js to self.skipWaiting(); on activation clientsClaim
    // fires controllerchange → reload. We do NOT reload here ourselves.
    const skipWaiting = (sw: ServiceWorker) => sw.postMessage({ type: 'SKIP_WAITING' })

    navigator.serviceWorker.getRegistration()
      .then((reg) => {
        if (reg?.waiting) {
          skipWaiting(reg.waiting)
        } else if (reg?.installing) {
          // Update still downloading — wait for it, then activate. Don't reload
          // into the old build in the meantime.
          const sw = reg.installing
          sw.addEventListener('statechange', () => {
            if (sw.state === 'installed') skipWaiting(sw)
          })
        } else {
          // Stale prompt — nothing pending to switch to; reload picks up
          // whatever is current.
          clearTimeout(backstop)
          forceReload()
        }
      })
      .catch(() => { clearTimeout(backstop); forceReload() })
  }, [updating])

  const playerVisible = usePlayerStore((s) => s.player.isPlayerVisible)

  if (!needRefresh || suppressed) return null

  return (
    <div
      role="status"
      aria-live="polite"
      className={`fixed right-4 left-4 sm:left-auto sm:bottom-4 z-[90] sm:max-w-[340px] animate-in fade-in slide-in-from-bottom-2 duration-200 ${playerVisible ? 'bottom-40' : 'bottom-20'}`}
    >
      <div className="flex items-start gap-3 rounded-[var(--radius-md)] border border-border bg-card/95 backdrop-blur p-3.5 shadow-lg shadow-black/30">
        <div className="grid place-items-center h-8 w-8 shrink-0 rounded-full bg-accent-info-soft text-accent-info">
          <ArrowUpCircle size={18} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-lg font-semibold text-foreground">有新版本可用</div>
          <p className="mt-0.5 text-xs leading-[1.5] text-muted-foreground">
            重新整理以載入最新內容與修正。
          </p>
          <div className="mt-2.5 flex items-center gap-2">
            <button
              type="button"
              onClick={handleUpdate}
              disabled={updating}
              className="inline-flex items-center justify-center rounded-md bg-accent-info px-3 py-1.5 text-xs font-semibold text-accent-info-foreground hover:opacity-90 transition-opacity disabled:opacity-60"
            >
              {updating ? '更新中…' : '立即更新'}
            </button>
            <button
              type="button"
              onClick={() => setNeedRefresh(false)}
              className="inline-flex items-center justify-center rounded-md px-2.5 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
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
