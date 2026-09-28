import { useCallback, useEffect, useState } from 'react'
import { useRegisterSW } from 'virtual:pwa-register/react'
import { ArrowUpCircle, X } from 'lucide-react'
import { usePlayerStore } from '@/store/usePlayerStore'
import { pickUpdateTarget } from '@/lib/swUpdateTarget'

const PWA_UPDATE_KEY = 'pwa-update-reload'
const SUPPRESS_MS = 10_000
// Anti-hang fallback only — NOT the normal reload path. The reload is driven by
// `controllerchange` (the new worker actually taking control); this timer just
// guarantees the 更新中… button can't dead-end if a worker never takes control
// (errored, or nothing was really pending). Long enough not to race a slow
// mobile install+activate — a shorter value reloaded into the still-active OLD
// worker, re-serving the stale build and looping the prompt (the bug this fixes).
const RELOAD_BACKSTOP_MS = 10_000
// Same anti-hang role while a worker is still DOWNLOADING its precache (several
// MB) when the user taps: 10 s is not enough on mobile, and firing early reloads
// into the old build.
const INSTALL_BACKSTOP_MS = 60_000
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
 * - Activate the NEWEST worker. When another deploy lands while one is already
 *   waiting, the registration holds `waiting` (N+1) AND `installing` (N+2);
 *   skipping `waiting` reloads into the already-stale N+1 and the prompt returns
 *   as soon as N+2 installs ("tapped 更新 twice, still old"). Selection lives in
 *   lib/swUpdateTarget.ts (check: `node src/lib/swUpdateTarget.check.ts`).
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
    let backstop = setTimeout(forceReload, RELOAD_BACKSTOP_MS)
    const rearmBackstop = (ms: number) => {
      clearTimeout(backstop)
      backstop = setTimeout(forceReload, ms)
    }

    // Tell the generated sw.js to self.skipWaiting(); on activation clientsClaim
    // fires controllerchange → reload. We do NOT reload here ourselves.
    const skipWaiting = (sw: ServiceWorker) => sw.postMessage({ type: 'SKIP_WAITING' })

    navigator.serviceWorker.getRegistration()
      .then((reg) => {
        const target = pickUpdateTarget(reg)
        if (!target) {
          // Stale prompt — nothing pending to switch to; reload picks up
          // whatever is current.
          clearTimeout(backstop)
          forceReload()
        } else if (target.ready) {
          skipWaiting(target.worker)
        } else {
          // A newer worker is still downloading — possibly on top of one that is
          // already waiting. Wait for the NEWEST one, then activate it; don't
          // reload into an older build in the meantime.
          const sw = target.worker
          rearmBackstop(INSTALL_BACKSTOP_MS)
          sw.addEventListener('statechange', () => {
            if (sw.state === 'installed') {
              rearmBackstop(RELOAD_BACKSTOP_MS)
              skipWaiting(sw)
            } else if (sw.state === 'redundant') {
              // Install failed. Fall back to the worker that was already
              // waiting, if any; else the backstop reloads.
              rearmBackstop(RELOAD_BACKSTOP_MS)
              if (reg?.waiting) skipWaiting(reg.waiting)
            }
          })
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
      {/* One row, ~52px. The three-line card this replaced stood 125px tall across the
          full width of a phone and covered page content for as long as it was up — a lot
          of the screen to spend saying a reload is available. The explanatory sentence
          and the separate 稍後 button are gone: the headline already says it, and ✕ was
          always the same action. */}
      <div className="flex items-center gap-2.5 rounded-[var(--radius-md)] border border-border bg-card/95 backdrop-blur py-2 pl-3 pr-2 shadow-lg shadow-black/30">
        <ArrowUpCircle size={16} className="shrink-0 text-accent-info" />
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">有新版本可用</span>
        <button
          type="button"
          onClick={handleUpdate}
          disabled={updating}
          className="shrink-0 inline-flex items-center justify-center rounded-md bg-accent-info px-3 py-1.5 text-xs font-semibold text-accent-info-foreground hover:opacity-90 transition-opacity disabled:opacity-60"
        >
          {updating ? '更新中…' : '立即更新'}
        </button>
        <button
          type="button"
          onClick={() => setNeedRefresh(false)}
          aria-label="稍後再說"
          className="shrink-0 grid place-items-center h-8 w-8 rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
        >
          <X size={15} />
        </button>
      </div>
    </div>
  )
}
