import { useCallback, useEffect } from 'react'
import { useRegisterSW } from 'virtual:pwa-register/react'
import { ArrowUpCircle, X } from 'lucide-react'

// Guard against reload loops: reload at most once per page life when the new
// service worker takes control.
let reloading = false
function hardReload() {
  if (reloading) return
  reloading = true
  window.location.reload()
}

/**
 * PWA update prompt (registerType: 'prompt').
 *
 * When a freshly-deployed service worker is detected it waits (skipWaiting is
 * OFF) and we surface an on-brand toast. Tapping 更新 calls
 * `updateServiceWorker(true)` which posts SKIP_WAITING → the new SW activates →
 * `controllerchange` fires → we reload once into the latest bundle. The earlier
 * prompt's button was broken because it never triggered SKIP_WAITING; this does.
 *
 * Also polls hourly so a long-open tab notices new deploys.
 */
export function PWAUpdatePrompt() {
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    immediate: true,
    onRegisteredSW(_swUrl, r) {
      if (import.meta.env.DEV) console.log('[PWA] service worker registered')
      if (r) {
        setInterval(() => {
          r.update().catch(() => {})
        }, 60 * 60 * 1000) // hourly update check
      }
    },
    onRegisterError(error) {
      console.error('[PWA] service worker registration error:', error)
    },
  })

  useEffect(() => {
    if (!('serviceWorker' in navigator)) return
    navigator.serviceWorker.addEventListener('controllerchange', hardReload)
    return () => navigator.serviceWorker.removeEventListener('controllerchange', hardReload)
  }, [])

  // Tapping 更新 must ALWAYS land the new bundle. The library path
  // (updateServiceWorker → SKIP_WAITING → controllerchange) only fires once the
  // new worker claims this page, so we belt-and-suspenders it: post SKIP_WAITING
  // directly, reload the moment the worker reports `activated`, and keep a timeout
  // fallback (a fresh navigation is served by the now-active worker either way).
  const handleUpdate = useCallback(async () => {
    try { updateServiceWorker(true) } catch { /* fall through to the manual path */ }

    if (!('serviceWorker' in navigator)) { hardReload(); return }
    try {
      const reg = await navigator.serviceWorker.getRegistration()
      if (reg) {
        if (!reg.waiting) await reg.update().catch(() => {})
        const waiting = reg.waiting
        if (waiting) {
          waiting.addEventListener('statechange', () => {
            if (waiting.state === 'activated') hardReload()
          })
          waiting.postMessage({ type: 'SKIP_WAITING' })
        }
      }
    } catch { /* ignore — the timeout below still reloads */ }

    // Backstop: if no SW signal arrives, reload anyway so the button is never a no-op.
    setTimeout(hardReload, 2500)
  }, [updateServiceWorker])

  if (!needRefresh) return null

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-4 right-4 left-4 sm:left-auto z-[60] sm:max-w-[340px] animate-in fade-in slide-in-from-bottom-2 duration-200"
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
              className="inline-flex items-center justify-center rounded-md bg-accent-info px-3 py-1.5 text-[12px] font-semibold text-accent-info-foreground hover:opacity-90 transition-opacity"
            >
              立即更新
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
