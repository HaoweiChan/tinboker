import { useEffect } from 'react'
import { useRegisterSW } from 'virtual:pwa-register/react'

// Guard against reload loops: reload at most once per page life when the new
// service worker takes control.
let reloading = false

/**
 * PWA auto-update. With `registerType: 'autoUpdate'` (+ skipWaiting/clientsClaim),
 * a freshly-deployed service worker activates and claims the page immediately,
 * firing `controllerchange` — at which point we reload once so the user always
 * gets the latest bundle without a manual "update" tap. Also polls hourly so a
 * long-open tab picks up new deploys.
 *
 * Renders nothing (no UI prompt).
 */
export function PWAUpdatePrompt() {
  useRegisterSW({
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
    const onControllerChange = () => {
      if (reloading) return
      reloading = true
      window.location.reload()
    }
    navigator.serviceWorker.addEventListener('controllerchange', onControllerChange)
    return () => navigator.serviceWorker.removeEventListener('controllerchange', onControllerChange)
  }, [])

  return null
}
