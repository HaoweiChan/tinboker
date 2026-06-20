import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Home, Mic, LineChart, TrendingUp, Hash, Info, MessageSquareText, Bookmark } from 'lucide-react';
import { cn } from '@/lib/utils';
import { AppLogo } from '@/components/logo/AppLogo';
import { useUser } from '@/store/useAppStore';

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  /** Match by prefix (detail routes) rather than exact. */
  prefix?: boolean;
  /** For /profile deep-links: the tab this item maps to (active when ?tab= matches). */
  tab?: string;
  /** Surfaced only on dev.tinboker.com (VITE_STAGE=DEV); hidden on staging/prod. */
  devOnly?: boolean;
}

// Mirrors App.tsx route gating: dev-only nav entries appear on dev.tinboker.com only.
const IS_DEV_ENV = (import.meta.env.VITE_STAGE as string) === 'DEV';

interface NavSection {
  /** Group heading, shown only when the sidebar is expanded. */
  title: string;
  items: readonly NavItem[];
}

/** Standalone anchor pinned above the grouped sections. */
const HOME: NavItem = { to: '/', label: '首頁', icon: Home };

const SECTIONS: readonly NavSection[] = [
  {
    title: '探索',
    items: [
      { to: '/podcaster', label: '節目', icon: Mic, prefix: true },
      { to: '/stock', label: '個股', icon: LineChart, prefix: true },
      { to: '/picks', label: '走勢', icon: TrendingUp, prefix: true, devOnly: true },
      { to: '/topics', label: '話題', icon: Hash, prefix: true },
      // 文章 (articles) hidden from nav until at least one article is published —
      // the /articles route still works, it just isn't surfaced while empty.
    ],
  },
  {
    title: '我的',
    items: [
      { to: '/profile?tab=podcasters', label: '訂閱節目', icon: Mic, tab: 'podcasters' },
      { to: '/profile?tab=tickers', label: '自選個股', icon: LineChart, tab: 'tickers' },
      { to: '/profile?tab=topics', label: '追蹤話題', icon: Hash, tab: 'topics' },
      { to: '/profile?tab=episodes', label: '收藏集數', icon: Bookmark, tab: 'episodes' },
    ],
  },
  {
    title: '支援',
    items: [
      { to: '/report', label: '意見回饋', icon: MessageSquareText },
      { to: '/about', label: '關於', icon: Info },
    ],
  },
];

function isActive(pathname: string, search: string, item: NavItem): boolean {
  if (item.tab) {
    return pathname === '/profile' && new URLSearchParams(search).get('tab') === item.tab;
  }
  if (item.to === '/') return pathname === '/';
  return item.prefix ? pathname === item.to || pathname.startsWith(item.to + '/') : pathname === item.to;
}

/**
 * Desktop sidebar. Sits collapsed (icon rail) by default and expands to a full
 * panel on hover — the panel floats over the page content so hovering never
 * shifts the layout. Grouped into labeled sections (ailogora-style).
 */
export const Sidebar: React.FC = () => {
  const { pathname, search } = useLocation();
  const user = useUser();
  const [expanded, setExpanded] = useState(false);

  const renderItem = (item: NavItem) => {
    const active = isActive(pathname, search, item);
    const Icon = item.icon;
    return (
      <Link
        key={item.to}
        to={item.to}
        aria-current={active ? 'page' : undefined}
        title={!expanded ? item.label : undefined}
        className={cn(
          'flex items-center gap-3.5 px-2.5 py-2.5 rounded-lg text-[14px] font-medium transition-colors',
          !expanded && 'justify-center px-0',
          active ? 'bg-muted text-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground',
        )}
      >
        <Icon size={18} className="shrink-0 opacity-85" />
        {expanded && <span className="truncate">{item.label}</span>}
      </Link>
    );
  };

  return (
    // Fixed-width rail in the grid (no layout shift); the inner panel overlays on hover.
    <aside className="hidden lg:block sticky top-0 h-screen w-[64px] shrink-0 z-30">
      <div
        onMouseEnter={() => setExpanded(true)}
        onMouseLeave={() => setExpanded(false)}
        className={cn(
          'absolute inset-y-0 left-0 flex flex-col border-r border-border bg-card py-5 transition-[width,box-shadow] duration-200 ease-in-out',
          expanded ? 'w-[248px] px-3.5 shadow-2xl' : 'w-[64px] px-2',
        )}
      >
        {/* Brand */}
        <div
          className={cn(
            'flex items-center pt-1 pb-4 mb-3 border-b border-border',
            expanded ? 'px-1' : 'justify-center',
          )}
        >
          <Link
            to="/"
            title="聽播客 TinBoker"
            className="flex items-center gap-2 hover:opacity-80 transition-opacity"
          >
            <AppLogo size={26} markOnly={!expanded} />
          </Link>
        </div>

        {/* Standalone home anchor */}
        <nav className="flex flex-col">{renderItem(HOME)}</nav>

        {/* Grouped sections */}
        {SECTIONS.map((section) => (
          <div key={section.title}>
            {expanded ? (
              <div className="text-[10px] font-semibold tracking-[0.09em] uppercase text-muted-foreground/80 px-2.5 pt-6 pb-2">
                {section.title}
              </div>
            ) : (
              <div className="mx-2.5 my-3 h-px bg-border" />
            )}
            <nav className="flex flex-col gap-1">
              {section.items.filter((it) => IS_DEV_ENV || !it.devOnly).map(renderItem)}
            </nav>
          </div>
        ))}

        {/* Footer: user / login */}
        <div className="mt-auto pt-4 border-t border-border">
          {user ? (
            <Link
              to="/profile"
              title={!expanded ? `${user.name || '使用者'} · ${user.email}` : '個人檔案'}
              className={cn(
                'flex items-center gap-2.5 rounded-lg hover:bg-muted/50 transition-colors',
                expanded ? 'px-1.5 py-1' : 'justify-center px-0 py-1',
              )}
            >
              <span className="w-7 h-7 rounded-full overflow-hidden grid place-items-center text-[11px] font-semibold text-white shrink-0 bg-accent-info">
                {user.avatar ? (
                  <img
                    src={user.avatar}
                    alt={`Avatar of ${user.name}`}
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                ) : (
                  (user.initials || user.name || user.email || '?').charAt(0).toUpperCase()
                )}
              </span>
              {expanded && (
                <span className="min-w-0">
                  <span className="block text-[13px] font-medium truncate">{user.name || '使用者'}</span>
                  <span className="block text-[11px] text-muted-foreground truncate">{user.email}</span>
                </span>
              )}
            </Link>
          ) : (
            expanded && <span className="block px-1.5 text-[12px] text-muted-foreground">尚未登入</span>
          )}
        </div>

        {/* App version */}
        {expanded && (
          <div className="px-2.5 pt-3 text-[10px] text-muted-foreground/50 tracking-wide tabular-nums">
            {__APP_VERSION__}
          </div>
        )}
      </div>
    </aside>
  );
};
