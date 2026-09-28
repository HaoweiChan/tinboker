import React from 'react';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { BottomTabs } from './BottomTabs';
import { SearchDropdown } from '@/components/ui/SearchDropdown';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { NotificationDropdown } from '@/components/ui/NotificationDropdown';
import { UserMenu } from '@/components/ui/UserMenu';
import { BracketMark } from '@/components/logo/AppLogo';
import { OnboardingModals } from '@/components/onboarding/OnboardingModals';
import { LoginPromptModal } from '@/components/auth/LoginPromptModal';
import { MembershipPreviewBanner } from '@/components/auth/MembershipPreviewBanner';
import { usePlayerStore } from '@/store/usePlayerStore';

/** [title, subtitle] for the page header, derived from the route. */
function pageTitle(pathname: string): [string, string] {
  const seg = pathname.split('/').filter(Boolean);
  const root = '/' + (seg[0] ?? '');
  const hasId = seg.length > 1;
  switch (root) {
    case '/':
      return ['首頁', ''];
    case '/podcaster':
      return hasId ? ['節目', '節目訂閱與分析'] : ['節目', '所有財經 Podcast'];
    case '/stock':
      return hasId ? ['個股', '個股情緒與相關集數'] : ['個股', '所有被提及的個股'];
    case '/topics':
      return hasId ? ['話題', '相關集數與個股'] : ['話題', '熱門 hashtag'];
    case '/watchlist':
      return ['自選', '追蹤的節目與個股'];
    case '/member':
      return ['會員專區', '訂閱、收藏與走勢功能'];
    case '/episode':
      return ['集數摘要', '結構化重點 · 關鍵片段'];
    case '/news':
      return ['集數', '摘要 · 相關內容'];
    case '/settings':
      return ['帳號設定', '顯示、通知與偏好'];
    case '/story':
      return ['探索', '知識圖譜'];
    case '/industry':
      return ['產業', '產業概覽'];
    case '/about':
      return ['關於', '聯絡我們 · 免責聲明'];
    default:
      return ['TinBoker', ''];
  }
}

/**
 * App shell: left sidebar (desktop) + sticky top header + page content (<Outlet/>) + bottom tabs (mobile).
 * Wraps all consumer routes; /admin keeps its own layout.
 *
 * The sidebar is a fixed 64px icon rail that expands to a floating panel on hover,
 * so the grid column width is constant and page content never shifts.
 */
export const AppLayout: React.FC = () => {
  const { pathname } = useLocation();
  const [title, subtitle] = pageTitle(pathname);
  const playerVisible = usePlayerStore((s) => s.player.isPlayerVisible);

  return (
    // The sidebar column widens at xl, where the rail stays open with its labels
    // visible; below that it is a 64px rail whose hover panel floats over the content.
    <div className="min-h-screen lg:grid lg:grid-cols-[64px_1fr] xl:grid-cols-[248px_1fr] bg-background">
      {/* Keyboard users otherwise tab the 10-item sidebar rail and the header on every
          page before reaching the content. Off-screen until focused, so it costs the
          visual design nothing. */}
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] focus:rounded-[3px] focus:border focus:border-accent-info focus:bg-card focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-foreground"
      >
        跳到主要內容
      </a>
      <Sidebar />
      <div className="flex flex-col min-w-0 min-h-screen">
        {/* z-30 matches the other app chrome (Sidebar, BottomTabs). At z-20 the header tied
            with page content — chart legends (TradingViewChart z-20) come later in the DOM and
            painted over the open header dropdowns. Modals/overlays stay above at z-40+. */}
        <header className="sticky top-0 z-30 border-b border-border bg-background/85 backdrop-blur supports-[backdrop-filter]:bg-background/70">
          <div className="flex items-center gap-2 sm:gap-4 px-4 sm:px-6 lg:px-7 py-2 sm:py-3 max-w-[1440px] mx-auto w-full">
            <Link to="/" className="lg:hidden shrink-0" aria-label="首頁">
              <BracketMark size={28} />
            </Link>
            <div className="hidden sm:flex items-baseline gap-2 shrink-0">
              <span className="text-lg sm:text-xl font-semibold tracking-[-0.01em] whitespace-nowrap">{title}</span>
              {subtitle && <span className="hidden md:inline text-xs text-muted-foreground font-medium">{subtitle}</span>}
            </div>
            <div className="flex-1 min-w-0 max-w-xl lg:mx-auto">
              <SearchDropdown />
            </div>
            <div className="flex items-center gap-1.5 sm:gap-2 shrink-0 ml-auto">
              <ThemeToggle />
              <NotificationDropdown />
              <UserMenu />
            </div>
          </div>
        </header>
        {import.meta.env.VITE_STAGE === 'DEV' && <MembershipPreviewBanner />}

        <main id="main" className={`flex-1 min-w-0${playerVisible ? ' pb-24 lg:pb-20' : ''}`}>
          <Outlet />
        </main>

        <BottomTabs />
      </div>
      <OnboardingModals />
      <LoginPromptModal />
    </div>
  );
};
