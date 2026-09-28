import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Home, Mic, LineChart, Crown, Hash, Info, CalendarDays } from 'lucide-react';
import { cn } from '@/lib/utils';
import { AppLogo } from '@/components/logo/AppLogo';
import { useUser } from '@/store/useAppStore';
import { useIsWide } from '@/hooks/useIsDesktop';

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  /** Match by prefix (detail routes) rather than exact. */
  prefix?: boolean;
  /** Surfaced only on dev.tinboker.com (VITE_STAGE=DEV); hidden on staging/prod. */
  devOnly?: boolean;
}

// Mirrors App.tsx route gating: dev-only nav entries appear on dev.tinboker.com only.
const IS_DEV_ENV = (import.meta.env.VITE_STAGE as string) === 'DEV';

interface NavSection {
  /** Group heading, shown only when the sidebar is expanded; omit for a plain divider. */
  title?: string;
  items: readonly NavItem[];
}

/** Standalone anchor pinned above the grouped sections. */
const TOP: readonly NavItem[] = [{ to: '/', label: '首頁', icon: Home }];

const SECTIONS: readonly NavSection[] = [
  {
    // Order matches the ExploreTabs switcher these three pages share.
    title: '探索',
    items: [
      { to: '/stock', label: '個股', icon: LineChart, prefix: true },
      { to: '/podcaster', label: '節目', icon: Mic, prefix: true },
      { to: '/topics', label: '話題', icon: Hash, prefix: true },
      { to: '/weekly', label: '週報', icon: CalendarDays, prefix: true },
      // 文章 (articles) hidden from nav until at least one article is published —
      // the /articles route still works, it just isn't surfaced while empty.
    ],
  },
  {
    // No heading: a top-level place like 首頁, grouped here only so the rail order
    // matches the mobile tab bar (首頁 · 探索 · 會員).
    items: [{ to: '/member', label: '會員', icon: Crown, prefix: true }],
  },
  {
    title: '支援',
    items: [
      // One page: 關於 / 聯絡我們 / 免責聲明 are sections of /about.
      { to: '/about', label: '關於', icon: Info },
    ],
  },
];

function isActive(pathname: string, item: NavItem): boolean {
  if (item.to === '/') return pathname === '/';
  const [base, hash] = item.to.split('#');
  if (hash) return pathname === base && window.location.hash === `#${hash}`;
  return item.prefix ? pathname === base || pathname.startsWith(base + '/') : pathname === base;
}

/**
 * Desktop sidebar. Grouped into labeled sections (ailogora-style).
 *
 * At `xl` and wider it stays open with its labels visible: below that the viewport
 * cannot spare 248px, so it collapses to a 64px icon rail that expands on hover, and
 * the expanded panel floats over the page content so hovering never shifts the layout.
 * Hover-only labels mean every destination has to be recognised from a bare glyph or
 * uncovered one at a time, which is a poor trade on a screen with room to just say it.
 */
export const Sidebar: React.FC = () => {
  const { pathname } = useLocation();
  const user = useUser();
  const pinned = useIsWide();
  const [hovered, setHovered] = useState(false);
  const expanded = pinned || hovered;

  const renderItem = (item: NavItem) => {
    const active = isActive(pathname, item);
    const Icon = item.icon;
    return (
      <Link
        key={item.to}
        to={item.to}
        aria-current={active ? 'page' : undefined}
        title={!expanded ? item.label : undefined}
        className={cn(
          'flex items-center gap-3.5 px-2.5 py-2.5 rounded-lg text-base font-medium transition-colors',
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
    // z-[35] beats the header's z-30 — at a tie the header comes later in the DOM and its
    // blurred bar painted over the expanded panel's brand row. Modals stay above at z-40+.
    <aside className="hidden lg:block sticky top-0 h-screen w-[64px] xl:w-[248px] shrink-0 z-[35]">
      <div
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        className={cn(
          'absolute inset-y-0 left-0 flex flex-col border-r border-border bg-card py-5 transition-[width,box-shadow] duration-200 ease-in-out',
          expanded ? 'w-[248px] px-3.5' : 'w-[64px] px-2',
          // Only the hover panel floats over the page and needs to lift off it; when
          // pinned the sidebar owns its grid column and a shadow would be a seam.
          hovered && !pinned && 'shadow-2xl',
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
        <nav className="flex flex-col gap-1">{TOP.map(renderItem)}</nav>

        {/* Grouped sections */}
        {SECTIONS.map((section) => (
          <div key={section.title}>
            {expanded && section.title ? (
              <div className="text-2xs font-semibold tracking-[0.09em] uppercase text-muted-foreground/80 px-2.5 pt-6 pb-2">
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
              to="/member"
              title={!expanded ? `${user.name || '使用者'} · ${user.email}` : '會員專區'}
              className={cn(
                'flex items-center gap-2.5 rounded-lg hover:bg-muted/50 transition-colors',
                expanded ? 'px-1.5 py-1' : 'justify-center px-0 py-1',
              )}
            >
              <span className="w-7 h-7 rounded-full overflow-hidden grid place-items-center text-2xs font-semibold text-white shrink-0 bg-accent-info">
                {user.avatar ? (
                  <img
                    src={user.avatar}
                    alt={`Avatar of ${user.name}`}
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                ) : (
                  (user?.initials || user?.name || user?.email || '?').charAt(0).toUpperCase()
                )}
              </span>
              {expanded && (
                <span className="min-w-0">
                  <span className="block text-sm font-medium truncate">{user.name || '使用者'}</span>
                  <span className="block text-2xs text-muted-foreground truncate">{user.email}</span>
                </span>
              )}
            </Link>
          ) : (
            expanded && <span className="block px-1.5 text-xs text-muted-foreground">尚未登入</span>
          )}
        </div>

        {/* App version */}
        {expanded && (
          <div className="px-2.5 pt-3 text-2xs text-muted-foreground/50 tracking-wide tabular-nums">
            {__APP_VERSION__}
          </div>
        )}
      </div>
    </aside>
  );
};
