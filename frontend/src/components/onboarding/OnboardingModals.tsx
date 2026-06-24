import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { X, ArrowRight, ArrowLeft, TrendingUp, Hash, Sparkles } from 'lucide-react';
import { useAppStore } from '@/store/useAppStore';
import { BracketMark } from '@/components/logo/AppLogo';
import { GoogleLoginButton } from '@/components/auth/GoogleLoginButton';
import {
  CHANGELOG,
  hasSeenOnboarding,
  markOnboardingSeen,
  markChangelogSeen,
  unseenChangelog,
  type ChangelogEntry,
} from '@/lib/onboarding';

/* ── Terminal-window shell ──────────────────────────────────────────────────
   Purpose-built (not the generic <Modal>) so we control the full terminal
   aesthetic: title bar, hero visual, sharp corners, mono type. */

const GRID_BG: React.CSSProperties = {
  backgroundImage:
    'linear-gradient(hsl(var(--border)) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--border)) 1px, transparent 1px)',
  backgroundSize: '18px 18px',
  opacity: 0.35,
};

const primaryBtn =
  'inline-flex items-center gap-1.5 px-4 py-2 rounded-sm bg-primary text-primary-foreground text-sm font-bold hover:opacity-90 transition';

function Shell({
  label,
  onClose,
  children,
}: {
  label: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onEsc);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onEsc);
      document.body.style.overflow = 'unset';
    };
  }, [onClose]);

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-200"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="w-full max-w-md bg-popover border border-border rounded-md shadow-xl overflow-hidden font-mono animate-in zoom-in-95 duration-200">
        {/* terminal title bar */}
        <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-card">
          <span className="flex gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-primary" />
            <span className="w-2.5 h-2.5 rounded-full bg-accent-info" />
            <span className="w-2.5 h-2.5 rounded-full bg-muted-foreground/40" />
          </span>
          <span className="text-2xs text-muted-foreground tracking-wide ml-1">{label}</span>
          <button
            onClick={onClose}
            className="ml-auto p-1 rounded-sm hover:bg-muted text-muted-foreground transition-colors"
            aria-label="關閉"
          >
            <X size={15} />
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}

/* ── Per-slide hero visuals — mini-mockups of the real screens ──────────────── */

function Hero({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative h-44 flex items-center justify-center px-6 bg-background overflow-hidden border-b border-border">
      <div className="absolute inset-0" style={GRID_BG} />
      <div className="relative w-full">{children}</div>
    </div>
  );
}

const tape = [
  { s: '2330', d: 'up' },
  { s: 'NVDA', d: 'up' },
  { s: '2454', d: 'down' },
  { s: '0050', d: 'up' },
];

function HeroWelcome() {
  return (
    <Hero>
      <div className="flex flex-col items-center gap-3">
        <BracketMark size={44} />
        <div className="flex items-baseline gap-1.5">
          <span className="text-base font-bold text-foreground" style={{ fontFamily: "'Noto Sans TC', sans-serif" }}>
            聽播客
          </span>
          <span className="text-base font-bold text-foreground">TinBoker</span>
        </div>
        <div className="flex gap-1.5">
          {tape.map((t) => (
            <span
              key={t.s}
              className={`px-1.5 py-0.5 rounded-sm text-2xs font-bold tabular-nums ${
                t.d === 'up'
                  ? 'bg-sentiment-bull-soft text-sentiment-bull'
                  : 'bg-sentiment-bear-soft text-sentiment-bear'
              }`}
            >
              {t.s} {t.d === 'up' ? '▲' : '▼'}
            </span>
          ))}
        </div>
      </div>
    </Hero>
  );
}

function HeroStock() {
  return (
    <Hero>
      {/* mock ticker-insight card */}
      <div className="mx-auto max-w-[15rem] bg-card border border-border rounded-sm p-3 shadow-sm space-y-2.5">
        <div className="flex items-center gap-2">
          <span className="text-base font-bold text-primary tabular-nums">2330</span>
          <span className="text-xs text-muted-foreground" style={{ fontFamily: "'Noto Sans TC', sans-serif" }}>
            台積電
          </span>
          <span className="ml-auto inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-2xs font-bold bg-sentiment-bull-soft text-sentiment-bull">
            <TrendingUp size={11} /> 看多
          </span>
        </div>
        <div className="h-1.5 rounded-full overflow-hidden flex">
          <span className="bg-sentiment-bull" style={{ width: '68%' }} />
          <span className="bg-sentiment-neutral/40" style={{ width: '20%' }} />
          <span className="bg-sentiment-bear" style={{ width: '12%' }} />
        </div>
        <div className="flex flex-wrap gap-1">
          {['AI', '半導體', '先進製程'].map((t) => (
            <span
              key={t}
              className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-sm text-2xs border border-border text-accent-info"
            >
              <Hash size={9} />
              <span style={{ fontFamily: "'Noto Sans TC', sans-serif" }}>{t}</span>
            </span>
          ))}
        </div>
      </div>
    </Hero>
  );
}

function HeroEpisode() {
  return (
    <Hero>
      {/* mock episode-summary card */}
      <div className="mx-auto max-w-[15rem] bg-card border border-border rounded-sm p-3 shadow-sm space-y-2.5">
        <div className="flex items-center gap-2">
          <span className="w-7 h-7 rounded-sm bg-primary/90 grid place-items-center text-primary-foreground text-2xs font-bold">
            EP
          </span>
          <div className="space-y-1">
            <span className="block w-28 h-2 rounded-sm bg-foreground/80" />
            <span className="block w-16 h-1.5 rounded-sm bg-muted-foreground/40" />
          </div>
          <Sparkles size={13} className="ml-auto text-primary" />
        </div>
        <div className="space-y-1.5">
          {['80%', '95%', '70%'].map((w, i) => (
            <div key={i} className="flex items-center gap-1.5">
              <span className="w-1 h-1 rounded-full bg-accent-info shrink-0" />
              <span className="h-1.5 rounded-sm bg-muted-foreground/30" style={{ width: w }} />
            </div>
          ))}
        </div>
      </div>
    </Hero>
  );
}

const sectors = [
  { n: '半導體', d: 'up', v: '+2.4%' },
  { n: 'AI 伺服器', d: 'up', v: '+3.1%' },
  { n: '金融', d: 'down', v: '-1.1%' },
  { n: '航運', d: 'up', v: '+0.8%' },
];

function HeroSector() {
  return (
    <Hero>
      {/* mock sector overview grid */}
      <div className="mx-auto max-w-[15rem] grid grid-cols-2 gap-1.5">
        {sectors.map((s) => (
          <div key={s.n} className="bg-card border border-border rounded-sm px-2 py-1.5 flex items-center gap-1.5">
            <span
              className={`w-1 h-6 rounded-full shrink-0 ${s.d === 'up' ? 'bg-sentiment-bull' : 'bg-sentiment-bear'}`}
            />
            <div className="min-w-0">
              <span className="block text-2xs text-foreground truncate" style={{ fontFamily: "'Noto Sans TC', sans-serif" }}>
                {s.n}
              </span>
              <span
                className={`block text-2xs font-bold tabular-nums ${
                  s.d === 'up' ? 'text-sentiment-bull' : 'text-sentiment-bear'
                }`}
              >
                {s.v}
              </span>
            </div>
          </div>
        ))}
      </div>
    </Hero>
  );
}

const SLIDES = [
  {
    label: 'tinboker — 歡迎',
    Visual: HeroWelcome,
    title: '歡迎使用 TinBoker',
    body: '我們從財經 Podcast 中擷取個股情緒、熱門話題與重點摘要，讓你不用聽完整集也能掌握市場脈動。',
  },
  {
    label: 'tinboker — 個股 × 話題',
    Visual: HeroStock,
    title: '個股情緒 × 熱門話題',
    body: '每檔個股都標記了節目中的看多／看空情緒與相關話題，點 # 標籤即可探索同主題的所有集數與標的。',
  },
  {
    label: 'tinboker — 產業類股',
    Visual: HeroSector,
    title: '產業類股全景',
    body: '想掌握資金往哪流？產業頁彙整每個類股族群的相關個股與整體情緒，一眼看出族群輪動。',
  },
  {
    label: 'tinboker — 集數摘要',
    Visual: HeroEpisode,
    title: '結構化集數摘要',
    body: '每集節目都拆解成關鍵重點與片段，登入後還能追蹤自選個股、訂閱節目並收藏集數。',
  },
];

/* ── Controller ─────────────────────────────────────────────────────────────
   Mounted once in the consumer shell. Tutorial → first-time / newly-registered
   users; otherwise a "what's new" panel after a release. */

type View = 'tutorial' | { entry: ChangelogEntry } | null;

export const OnboardingModals: React.FC = () => {
  const isAuthReady = useAppStore((s) => s.isAuthReady);
  const user = useAppStore((s) => s.user);
  const [view, setView] = useState<View>(null);
  const [step, setStep] = useState(0);
  // Preview mode (?onboarding=…) — show on demand without reading/writing the
  // "seen" flags, so you can eyeball a release's changelog before shipping.
  const [preview, setPreview] = useState(false);

  useEffect(() => {
    if (!isAuthReady) return;
    const force = new URLSearchParams(window.location.search).get('onboarding');
    if (force === 'tutorial' || force === 'whatsnew') {
      setPreview(true);
      setStep(0);
      setView(force === 'tutorial' ? 'tutorial' : CHANGELOG[0] ? { entry: CHANGELOG[0] } : null);
      return;
    }
    if (!hasSeenOnboarding()) {
      setStep(0);
      setView('tutorial');
      return;
    }
    const entry = unseenChangelog();
    setView(entry ? { entry } : null);
  }, [isAuthReady, user?.id]);

  if (view === 'tutorial') {
    const slide = SLIDES[step];
    const last = step === SLIDES.length - 1;
    const close = () => {
      if (!preview) {
        markOnboardingSeen();
        markChangelogSeen(); // new users shouldn't also get a changelog popup
      }
      setView(null);
    };
    return (
      <Shell label={slide.label} onClose={close}>
        <slide.Visual />
        <div className="p-5 space-y-4">
          <h2 className="text-lg font-bold text-foreground" style={{ fontFamily: "'Noto Sans TC', sans-serif" }}>
            {slide.title}
          </h2>
          <p
            className="text-sm text-muted-foreground leading-relaxed"
            style={{ fontFamily: "'Noto Sans TC', sans-serif" }}
          >
            {slide.body}
          </p>
          <div className="flex items-center justify-between gap-3 pt-1">
            <div className="flex items-center gap-3">
              <div className="flex gap-1.5">
                {SLIDES.map((_, i) => (
                  <button
                    key={i}
                    onClick={() => setStep(i)}
                    aria-label={`第 ${i + 1} 步`}
                    className={`h-1.5 rounded-full transition-all ${
                      i === step ? 'w-6 bg-primary' : 'w-1.5 bg-border hover:bg-muted-foreground/50'
                    }`}
                  />
                ))}
              </div>
              {!last && (
                <button onClick={close} className="text-xs text-muted-foreground hover:text-foreground transition">
                  略過
                </button>
              )}
            </div>
            <div className="flex items-center gap-2">
              {step > 0 && (
                <button
                  onClick={() => setStep(step - 1)}
                  className="inline-flex items-center gap-1 px-3 py-2 rounded-sm border border-border text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition"
                >
                  <ArrowLeft size={14} /> 上一步
                </button>
              )}
              {last ? (
                user ? (
                  <button onClick={close} className={primaryBtn}>
                    開始使用 <ArrowRight size={15} />
                  </button>
                ) : (
                  // Mark seen on click so registering here doesn't re-trigger the
                  // tutorial once the user logs in (login bypasses the close handler).
                  <span onClickCapture={() => !preview && markOnboardingSeen()}>
                    <GoogleLoginButton className={primaryBtn}>登入 / 註冊</GoogleLoginButton>
                  </span>
                )
              ) : (
                <button onClick={() => setStep(step + 1)} className={primaryBtn}>
                  下一步 <ArrowRight size={15} />
                </button>
              )}
            </div>
          </div>
        </div>
      </Shell>
    );
  }

  if (view && 'entry' in view) {
    const { entry } = view;
    const close = () => {
      if (!preview) markChangelogSeen();
      setView(null);
    };
    return (
      <Shell label={`tinboker — 更新內容`} onClose={close}>
        <div className="p-5 space-y-4">
          <div className="flex items-center gap-2">
            <Sparkles size={18} className="text-primary" />
            <h2 className="text-lg font-bold text-foreground" style={{ fontFamily: "'Noto Sans TC', sans-serif" }}>
              新版本上線
            </h2>
            <span className="ml-auto px-2 py-0.5 rounded-full text-2xs font-bold bg-primary text-primary-foreground tabular-nums">
              v{entry.version}
            </span>
          </div>
          <ul className="space-y-2">
            {entry.items.map((item, i) => (
              <li
                key={i}
                className="flex gap-2 text-sm text-muted-foreground"
                style={{ fontFamily: "'Noto Sans TC', sans-serif" }}
              >
                <span className="text-accent-info shrink-0 font-mono">▹</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
          <div className="flex justify-end pt-1">
            <button onClick={close} className={primaryBtn}>
              知道了
            </button>
          </div>
        </div>
      </Shell>
    );
  }

  return null;
};
