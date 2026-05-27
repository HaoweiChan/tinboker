import React from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { BottomTabs } from './BottomTabs';
import { SearchDropdown } from '@/components/ui/SearchDropdown';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { NotificationDropdown } from '@/components/ui/NotificationDropdown';
import { UserMenu } from '@/components/ui/UserMenu';

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
    case '/episode':
      return ['集數摘要', '結構化重點 · 關鍵片段'];
    case '/news':
      return ['集數', '摘要 · 相關內容'];
    case '/profile':
      return ['個人檔案', '訂閱、收藏與留言'];
    case '/settings':
      return ['帳號設定', '顯示、通知與偏好'];
    case '/story':
      return ['探索', '知識圖譜'];
    case '/industry':
      return ['產業', '產業概覽'];
    case '/about':
      return ['關於', '關於 TinBoker'];
    case '/contact':
      return ['聯絡我們', ''];
    case '/disclaimer':
      return ['免責聲明', ''];
    default:
      return ['TinBoker', ''];
  }
}

/**
 * App shell: left sidebar (desktop) + sticky top header + page content (<Outlet/>) + bottom tabs (mobile).
 * Wraps all consumer routes; /admin keeps its own layout.
 */
export const AppLayout: React.FC = () => {
  const { pathname } = useLocation();
  const [title, subtitle] = pageTitle(pathname);

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[220px_1fr] bg-background">
      <Sidebar />
      <div className="flex flex-col min-w-0 min-h-screen">
        <header className="sticky top-0 z-20 border-b border-border bg-background/85 backdrop-blur supports-[backdrop-filter]:bg-background/70">
          <div className="flex items-center gap-2 sm:gap-4 px-4 sm:px-6 lg:px-7 py-2 sm:py-3 max-w-[1440px] mx-auto w-full">
            <div className="hidden sm:flex items-baseline gap-2 shrink-0">
              <span className="text-[16px] sm:text-[18px] font-semibold tracking-[-0.01em] whitespace-nowrap">{title}</span>
              {subtitle && <span className="hidden md:inline text-[12px] text-muted-foreground font-medium">{subtitle}</span>}
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

        {/* Each page owns its own content container — PageContent for redesigned pages. */}
        <main className="flex-1 min-w-0">
          <Outlet />
        </main>

        <BottomTabs />
      </div>
    </div>
  );
};
