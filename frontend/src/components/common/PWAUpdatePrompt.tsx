import { useRegisterSW } from 'virtual:pwa-register/react'
import { RefreshCw, X } from 'lucide-react'

export function PWAUpdatePrompt() {
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegistered(r) {
      if (import.meta.env.DEV) console.log('[PWA] Service worker registered:', r)
    },
    onRegisterError(error) {
      console.error('[PWA] Service worker registration error:', error)
    },
  })

  const close = () => {
    setNeedRefresh(false)
  }

  const handleUpdate = () => {
    updateServiceWorker(true)
  }

  if (!needRefresh) {
    return null
  }

  return (
    <div className="fixed bottom-4 left-4 right-4 z-50 mx-auto max-w-md animate-slide-up">
      <div className="flex items-center gap-3 rounded-lg border border-accent-info/30 bg-slate-900/95 px-4 py-3 shadow-lg backdrop-blur-sm">
        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-accent-info/20">
          <RefreshCw className="h-5 w-5 text-accent-info" />
        </div>
        <div className="flex-1">
          <p className="text-sm font-medium text-slate-100">有新版本可用</p>
          <p className="text-xs text-slate-400">點擊更新以獲得最新功能</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleUpdate}
            className="rounded-md bg-accent-info px-3 py-1.5 text-sm font-medium text-slate-900 transition-colors hover:bg-accent-info"
          >
            更新
          </button>
          <button
            onClick={close}
            className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-200"
            aria-label="關閉"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
