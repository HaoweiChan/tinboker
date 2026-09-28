import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Home, Compass, Crown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { EXPLORE_ITEMS } from '@/lib/nav';

interface Tab {
  to: string;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  prefix: boolean;
  /** Extra route prefixes that keep this tab lit (one tab standing for several pages). */
  also?: readonly string[];
  /** Surfaced only on dev.tinboker.com (VITE_STAGE=DEV); hidden on staging/prod. */
  devOnly?: boolean;
}

// Three tabs, one per top-level place — mirrored by the sidebar's groups so mobile and
// desktop offer the same shape. Everything browsable (個股 / 節目 / 話題 / 週報) lives
// behind 探索 and switches via ExploreTabs, so every tab here is free to use; 走勢 and
// 收藏 are inside /member. Well under the 5-tab ceiling, with room to promote something.
const TABS: readonly Tab[] = [
  { to: '/', label: '首頁', icon: Home, prefix: false },
  { to: EXPLORE_ITEMS[0].to, label: '探索', icon: Compass, prefix: true, also: EXPLORE_ITEMS.slice(1).map((i) => i.to) },
  // 會員 is the permanent sales surface for non-members and their hub once they join.
  { to: '/member', label: '會員', icon: Crown, prefix: true },
];

// Mirrors App.tsx route gating: dev-only tabs appear on dev.tinboker.com only.
const IS_DEV_ENV = (import.meta.env.VITE_STAGE as string) === 'DEV';

// Tailwind needs whole class names present at build time — map the visible-tab count
// to a static col class so the bar stays a single clean row.
const GRID_COLS: Record<number, string> = { 3: 'grid-cols-3', 4: 'grid-cols-4', 5: 'grid-cols-5' };

function active(pathname: string, t: Tab): boolean {
  const hit = (to: string) =>
    to === '/' ? pathname === '/' : t.prefix ? pathname === to || pathname.startsWith(to + '/') : pathname === to;
  return hit(t.to) || (t.also ?? []).some(hit);
}

/** Mobile-only bottom navigation bar. Hidden at `lg` and up (the sidebar takes over). */
export const BottomTabs: React.FC = () => {
  const { pathname } = useLocation();
  const tabs = TABS.filter((t) => IS_DEV_ENV || !t.devOnly);
  return (
    <nav className="lg:hidden sticky bottom-0 z-30 bg-card/95 backdrop-blur border-t border-border" style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}>
      <div className={cn('grid', GRID_COLS[tabs.length] ?? 'grid-cols-5')}>
        {tabs.map((t) => {
          const on = active(pathname, t);
          const Icon = t.icon;
          return (
            <Link
              key={t.to}
              to={t.to}
              aria-current={on ? 'page' : undefined}
              className={cn('flex flex-col items-center gap-0.5 py-2 text-2xs', on ? 'text-foreground' : 'text-muted-foreground')}
            >
              <Icon size={22} />
              <span>{t.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
};
