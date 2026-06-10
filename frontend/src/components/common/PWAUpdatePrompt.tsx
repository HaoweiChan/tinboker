import { useCallback, useEffect, useState } from 'react'
import { useRegisterSW } from 'virtual:pwa-register/react'
import { ArrowUpCircle, X } from 'lucide-react'

const PWA_UPDATE_KEY = 'pwa-update-reload'
const SUPPRESS_MS = 10_000

function forceReload() {
  sessionStorage.setItem(PWA_UPDATE_KEY, String(Date.now()))
  const url = new URL(window.location.href)
  url.searchParams.set('_t', String(Date.now()))
  window.location.href = url.toString()
}

/**
 * PWA update prompt (registerType: 'prompt').
 *
 * When a new service worker is detected we surface a toast. Tapping "立即更新"
 * posts SKIP_WAITING → new SW activates → controllerchange → force-reload.
 * A timeout backstop ensures the button ALWAYS navigates away (never a no-op).
 * Polls hourly so long-open tabs notice new deploys.
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
        setInterval(() => { r.update().catch(() => {}) }, 60 * 60 * 1000)
      }
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
    const handler = () => forceReload()
    navigator.serviceWorker.addEventListener('controllerchange', handler)
    return () => navigator.serviceWorker.removeEventListener('controllerchange', handler)
  }, [])

  const handleUpdate = useCallback(async () => {
    setUpdating(true)
    try { updateServiceWorker(true) } catch { /* fall through */ }

    if (!('serviceWorker' in navigator)) { forceReload(); return }
    try {
      const reg = await navigator.serviceWorker.getRegistration()
      if (reg) {
        if (!reg.waiting) await reg.update().catch(() => {})
        const waiting = reg.waiting
        if (waiting) {
          waiting.addEventListener('statechange', () => {
            if (waiting.state === 'activated') forceReload()
          })
          waiting.postMessage({ type: 'SKIP_WAITING' })
        }
      }
    } catch { /* ignore — timeout below handles it */ }

    // Backstop: force-reload after 2s regardless of SW state.
    setTimeout(forceReload, 2000)
  }, [updateServiceWorker])

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
