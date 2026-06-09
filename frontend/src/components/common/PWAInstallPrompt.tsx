import React, { useCallback, useEffect, useState } from 'react';
import { Download, Share, Plus, MoreVertical, X, Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import { BracketMark } from '@/components/logo/AppLogo';

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

type Platform = 'ios' | 'android' | 'desktop-chromium' | 'other';

function detectPlatform(): Platform {
  const ua = navigator.userAgent;
  const isIOS = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  if (isIOS) return 'ios';
  if (/Android/i.test(ua)) return 'android';
  if (/Chrome|Edg|Brave|Opera|Vivaldi/i.test(ua) && !/Firefox/i.test(ua)) return 'desktop-chromium';
  return 'other';
}

function isStandalone(): boolean {
  return window.matchMedia('(display-mode: standalone)').matches
    || ('standalone' in navigator && (navigator as { standalone?: boolean }).standalone === true);
}

const Step: React.FC<{ step: number; icon: React.ReactNode; text: string }> = ({ step, icon, text }) => (
  <div className="flex items-start gap-3 py-3">
    <div className="flex items-center justify-center w-7 h-7 rounded-full bg-accent-info/15 text-accent-info text-[12px] font-bold shrink-0">
      {step}
    </div>
    <div className="flex items-center gap-2 min-w-0 text-[13px] leading-[1.6] text-foreground">
      <span className="shrink-0 text-muted-foreground">{icon}</span>
      <span>{text}</span>
    </div>
  </div>
);

/** Inline PWA install guide — renders as a settings section card. */
export const PWAInstallSection: React.FC = () => {
  const [platform] = useState(detectPlatform);
  const [installed, setInstalled] = useState(isStandalone);
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [installing, setInstalling] = useState(false);

  useEffect(() => {
    const handler = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
    };
    window.addEventListener('beforeinstallprompt', handler);
    window.addEventListener('appinstalled', () => setInstalled(true));
    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);

  const handleNativeInstall = useCallback(async () => {
    if (!deferredPrompt) return;
    setInstalling(true);
    try {
      await deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      if (outcome === 'accepted') setInstalled(true);
    } finally {
      setDeferredPrompt(null);
      setInstalling(false);
    }
  }, [deferredPrompt]);

  if (installed) {
    return (
      <div className="flex items-center gap-3 py-4 text-[13px] text-muted-foreground">
        <div className="grid place-items-center w-8 h-8 rounded-full bg-green-500/15 text-green-500">
          <Check size={16} />
        </div>
        <span>聽播客 App 已安裝在您的裝置上</span>
      </div>
    );
  }

  if (deferredPrompt) {
    return (
      <div className="space-y-3 py-2">
        <p className="text-[13px] text-muted-foreground leading-[1.6]">
          將聽播客加入主畫面，享受全螢幕瀏覽、離線快取、更快的載入速度。
        </p>
        <button
          type="button"
          onClick={handleNativeInstall}
          disabled={installing}
          className={cn(
            'inline-flex items-center gap-2 rounded-lg px-4 py-2.5 text-[13px] font-semibold transition-colors',
            'bg-accent-info text-accent-info-foreground hover:opacity-90',
            installing && 'opacity-60 cursor-not-allowed',
          )}
        >
          <Download size={16} />
          {installing ? '安裝中…' : '安裝 App'}
        </button>
      </div>
    );
  }

  if (platform === 'ios') {
    return (
      <div className="space-y-1 py-2">
        <p className="text-[13px] text-muted-foreground leading-[1.6] mb-2">
          在 Safari 中將聽播客加入主畫面，即可像原生 App 一樣使用。
        </p>
        <Step step={1} icon={<Share size={15} />} text="點擊 Safari 底部的「分享」按鈕" />
        <Step step={2} icon={<Plus size={15} />} text="向下捲動，點擊「加入主畫面」" />
        <Step step={3} icon={<Check size={15} />} text="點擊右上角「新增」即完成" />
        <div className="mt-3 px-3 py-2.5 rounded-lg bg-muted/60 text-[12px] text-muted-foreground leading-[1.6]">
          提示：請使用 Safari 瀏覽器。其他瀏覽器（Chrome、Line 內建等）不支援此功能。
        </div>
      </div>
    );
  }

  if (platform === 'android') {
    return (
      <div className="space-y-1 py-2">
        <p className="text-[13px] text-muted-foreground leading-[1.6] mb-2">
          在 Chrome 中將聽播客加入主畫面，享受全螢幕體驗。
        </p>
        <Step step={1} icon={<MoreVertical size={15} />} text="點擊 Chrome 右上角的「更多選項」(三個點)" />
        <Step step={2} icon={<Download size={15} />} text="選擇「安裝應用程式」或「加入主畫面」" />
        <Step step={3} icon={<Check size={15} />} text="確認安裝即完成" />
      </div>
    );
  }

  if (platform === 'desktop-chromium') {
    return (
      <div className="space-y-1 py-2">
        <p className="text-[13px] text-muted-foreground leading-[1.6] mb-2">
          在電腦版 Chrome / Edge 中安裝聽播客桌面 App。
        </p>
        <Step step={1} icon={<Download size={15} />} text="點擊網址列右側的安裝圖示 (⊕)" />
        <Step step={2} icon={<Check size={15} />} text="在彈出視窗中點擊「安裝」即完成" />
        <div className="mt-3 px-3 py-2.5 rounded-lg bg-muted/60 text-[12px] text-muted-foreground leading-[1.6]">
          如果沒看到安裝圖示，請點擊右上角 ⋮ →「安裝聽播客…」
        </div>
      </div>
    );
  }

  return (
    <div className="py-2">
      <p className="text-[13px] text-muted-foreground leading-[1.6]">
        您的瀏覽器可能不支援 PWA 安裝。請使用 Chrome、Safari 或 Edge 瀏覽器開啟此網站。
      </p>
    </div>
  );
};

/** Floating banner that appears for mobile users who haven't installed the PWA. */
export const PWAInstallBanner: React.FC = () => {
  const [visible, setVisible] = useState(false);
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [platform] = useState(detectPlatform);
  const [showIOSTutorial, setShowIOSTutorial] = useState(false);

  useEffect(() => {
    if (isStandalone()) return;
    const dismissed = sessionStorage.getItem('pwa-banner-dismissed');
    if (dismissed) return;
    const isTouch = platform === 'ios' || platform === 'android';
    if (!isTouch) return;
    const timer = setTimeout(() => setVisible(true), 3000);
    return () => clearTimeout(timer);
  }, [platform]);

  useEffect(() => {
    const handler = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
    };
    window.addEventListener('beforeinstallprompt', handler);
    window.addEventListener('appinstalled', () => setVisible(false));
    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);

  const dismiss = useCallback(() => {
    setVisible(false);
    setShowIOSTutorial(false);
    sessionStorage.setItem('pwa-banner-dismissed', '1');
  }, []);

  const handleInstall = useCallback(async () => {
    if (deferredPrompt) {
      await deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      if (outcome === 'accepted') setVisible(false);
      setDeferredPrompt(null);
    } else if (platform === 'ios') {
      setShowIOSTutorial(true);
    }
  }, [deferredPrompt, platform]);

  if (!visible) return null;

  return (
    <div className="fixed bottom-20 left-3 right-3 sm:left-auto sm:right-4 sm:max-w-[360px] z-[55] animate-in fade-in slide-in-from-bottom-3 duration-300">
      <div className="relative rounded-xl border border-border bg-card/95 backdrop-blur-md shadow-xl shadow-black/25 overflow-hidden">
        <button
          type="button"
          onClick={dismiss}
          aria-label="關閉"
          className="absolute top-2.5 right-2.5 grid place-items-center h-7 w-7 rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-colors z-10"
        >
          <X size={14} />
        </button>
        {!showIOSTutorial ? (
          <div className="flex items-center gap-3.5 p-4 pr-10">
            <div className="grid place-items-center w-11 h-11 rounded-xl bg-[#0e1014] shrink-0">
              <BracketMark size={24} className="text-[#f1ead8]" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[14px] font-semibold text-foreground">安裝聽播客 App</div>
              <p className="text-[12px] text-muted-foreground leading-[1.5] mt-0.5">
                加入主畫面，享受更流暢的體驗
              </p>
              <button
                type="button"
                onClick={handleInstall}
                className="mt-2.5 inline-flex items-center gap-1.5 rounded-lg bg-accent-info px-3.5 py-1.5 text-[12px] font-semibold text-accent-info-foreground hover:opacity-90 transition-opacity"
              >
                <Download size={13} />
                {deferredPrompt ? '立即安裝' : '查看安裝步驟'}
              </button>
            </div>
          </div>
        ) : (
          <div className="p-4 pt-3">
            <div className="text-[14px] font-semibold text-foreground mb-2">在 Safari 中安裝</div>
            <Step step={1} icon={<Share size={14} />} text="點擊底部「分享」按鈕" />
            <Step step={2} icon={<Plus size={14} />} text="選擇「加入主畫面」" />
            <Step step={3} icon={<Check size={14} />} text="點擊「新增」" />
            <button
              type="button"
              onClick={dismiss}
              className="mt-2 w-full rounded-lg bg-muted py-2 text-[12px] font-medium text-foreground hover:bg-muted/80 transition-colors"
            >
              知道了
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
