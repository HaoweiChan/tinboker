import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Home, Mic, LineChart, TrendingUp, Hash, Star } from 'lucide-react';
import { cn } from '@/lib/utils';

const TABS = [
  { to: '/', label: '首頁', icon: Home, prefix: false },
  { to: '/podcaster', label: '節目', icon: Mic, prefix: true },
  { to: '/stock', label: '個股', icon: LineChart, prefix: true },
  { to: '/picks', label: '走勢', icon: TrendingUp, prefix: true },
  { to: '/topics', label: '話題', icon: Hash, prefix: true },
  { to: '/watchlist', label: '自選', icon: Star, prefix: false },
] as const;

function active(pathname: string, to: string, prefix: boolean): boolean {
  if (to === '/') return pathname === '/';
  return prefix ? pathname === to || pathname.startsWith(to + '/') : pathname === to;
}

/** Mobile-only bottom navigation bar. Hidden at `lg` and up (the sidebar takes over). */
export const BottomTabs: React.FC = () => {
  const { pathname } = useLocation();
  return (
    <nav className="lg:hidden sticky bottom-0 z-30 bg-card/95 backdrop-blur border-t border-border" style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}>
      <div className="grid grid-cols-5">
        {TABS.map((t) => {
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
