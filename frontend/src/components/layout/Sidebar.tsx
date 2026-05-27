import React, { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Home, Mic, LineChart, Hash, Star, Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import { AppLogo } from '@/components/logo/AppLogo';
import { useSubscriptions, useUser } from '@/store/useAppStore';
import { PodMark } from '@/components/redesign';
import { getSortedPodcasts } from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  /** Match by prefix (detail routes) rather than exact. */
  prefix?: boolean;
}

const NAV: readonly NavItem[] = [
  { to: '/', label: '首頁', icon: Home },
  { to: '/podcaster', label: '節目', icon: Mic, prefix: true },
  { to: '/stock', label: '個股', icon: LineChart, prefix: true },
  { to: '/topics', label: '話題', icon: Hash, prefix: true },
  { to: '/watchlist', label: '自選', icon: Star },
];


function isActive(pathname: string, item: NavItem): boolean {
  if (item.to === '/') return pathname === '/';
  return item.prefix ? pathname === item.to || pathname.startsWith(item.to + '/') : pathname === item.to;
}

export const Sidebar: React.FC = () => {
  const { pathname } = useLocation();
  const subscriptions = useSubscriptions();
  const user = useUser();
  const [imageMap, setImageMap] = useState<Map<string, string>>(new Map());

  useEffect(() => {
    if (subscriptions.length === 0) return;
    let alive = true;
    fetchWithFallback(() => getSortedPodcasts({ sortBy: 'updated_at', order: 'desc', limit: 200 }), [], 'getSortedPodcasts')
      .then((podcasts) => {
        if (!alive) return;
        const map = new Map<string, string>();
        for (const p of Array.isArray(podcasts) ? podcasts : []) {
          if (p.name && p.image_url) map.set(p.name, p.image_url);
        }
        setImageMap(map);
      })
      .catch(() => {});
    return () => { alive = false; };
  }, [subscriptions.length]);

  return (
    <aside className="hidden lg:flex flex-col sticky top-0 h-screen w-[220px] shrink-0 border-r border-border bg-card px-3.5 py-4.5 z-30">
      <Link to="/" className="flex items-center px-1 pt-1.5 pb-4 hover:opacity-80 transition-opacity">
        <AppLogo size={26} />
      </Link>

      <nav className="flex flex-col gap-0.5">
        {NAV.map((item) => {
          const active = isActive(pathname, item);
          const Icon = item.icon;
          return (
            <Link
              key={item.to}
              to={item.to}
              aria-current={active ? 'page' : undefined}
              className={cn(
                'flex items-center gap-3 px-2.5 py-2 rounded-lg text-[14px] font-medium transition-colors',
                active ? 'bg-muted text-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground',
              )}
            >
              <Icon size={18} className="shrink-0 opacity-85" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {subscriptions.length > 0 && (
        <>
          <div className="text-[10px] font-semibold tracking-[0.08em] uppercase text-muted-foreground px-2.5 pt-4.5 pb-2">追蹤中</div>
          <div className="flex flex-col gap-0.5 overflow-y-auto">
            {subscriptions.slice(0, 8).map((name) => (
              <Link
                key={name}
                to={`/podcaster/${encodeURIComponent(name)}`}
                className="flex items-center gap-3 px-2.5 py-1.5 rounded-lg text-[13px] text-foreground hover:bg-muted transition-colors"
              >
                {imageMap.get(name) ? (
                  <img src={imageMap.get(name)} alt="" className="w-[18px] h-[18px] rounded-[4px] object-cover shrink-0" />
                ) : (
                  <PodMark label={name.charAt(0)} kind="mute" size={18} />
                )}
                <span className="truncate">{name}</span>
              </Link>
            ))}
          </div>
        </>
      )}

      <Link to="/about" className="flex items-center gap-1.5 px-2 pb-2 text-[11px] text-muted-foreground hover:text-foreground transition-colors mt-auto">
        <Info size={12} className="opacity-70" />
        關於
      </Link>
      <div className="pt-3.5 border-t border-border flex items-center gap-2.5 px-1.5">
        {user ? (
          <>
            <div className="w-7 h-7 rounded-full grid place-items-center text-[11px] font-semibold text-white shrink-0 bg-accent-info">
              {(user.name || user.email || '?').charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0">
              <div className="text-[13px] font-medium truncate">{user.name || '使用者'}</div>
              <div className="text-[11px] text-muted-foreground truncate">{user.email}</div>
            </div>
          </>
        ) : (
          <span className="text-[12px] text-muted-foreground px-1">尚未登入</span>
        )}
      </div>
    </aside>
  );
};
