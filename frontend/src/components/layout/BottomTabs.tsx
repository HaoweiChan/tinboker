import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Home, Mic, LineChart, TrendingUp, Hash, Star } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Tab {
  to: string;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  prefix: boolean;
  /** Surfaced only on dev.tinboker.com (VITE_STAGE=DEV); hidden on staging/prod. */
  devOnly?: boolean;
}

const TABS: readonly Tab[] = [
  { to: '/', label: '首頁', icon: Home, prefix: false },
  { to: '/podcaster', label: '節目', icon: Mic, prefix: true },
  { to: '/stock', label: '個股', icon: LineChart, prefix: true },
  { to: '/picks', label: '走勢', icon: TrendingUp, prefix: true, devOnly: true },
  { to: '/topics', label: '話題', icon: Hash, prefix: true },
  { to: '/watchlist', label: '收藏', icon: Star, prefix: false },
];

// Mirrors App.tsx route gating: dev-only tabs appear on dev.tinboker.com only.
const IS_DEV_ENV = (import.meta.env.VITE_STAGE as string) === 'DEV';

// Tailwind needs whole class names present at build time — map the visible-tab count
// to a static col class (5 off-dev, 6 on dev) so the bar stays a single clean row.
const GRID_COLS: Record<number, string> = { 4: 'grid-cols-4', 5: 'grid-cols-5', 6: 'grid-cols-6' };

function active(pathname: string, to: string, prefix: boolean): boolean {
  if (to === '/') return pathname === '/';
  return prefix ? pathname === to || pathname.startsWith(to + '/') : pathname === to;
}

/** Mobile-only bottom navigation bar. Hidden at `lg` and up (the sidebar takes over). */
export const BottomTabs: React.FC = () => {
  const { pathname } = useLocation();
  const tabs = TABS.filter((t) => IS_DEV_ENV || !t.devOnly);
  return (
    <nav className="lg:hidden sticky bottom-0 z-30 bg-card/95 backdrop-blur border-t border-border" style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}>
      <div className={cn('grid', GRID_COLS[tabs.length] ?? 'grid-cols-5')}>
        {tabs.map((t) => {
          const on = active(pathname, t.to, t.prefix);
          const Icon = t.icon;
          return (
            <Link
              key={t.to}
              to={t.to}
              aria-current={on ? 'page' : undefined}
              className={cn('flex flex-col items-center gap-0.5 py-2 text-[10px]', on ? 'text-foreground' : 'text-muted-foreground')}
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
