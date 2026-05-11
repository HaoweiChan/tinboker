import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Home, Mic, LineChart, Hash, Star } from 'lucide-react';
import { cn } from '@/lib/utils';
import { AppLogo } from '@/components/logo/AppLogo';
import { useSubscriptions, useUser } from '@/store/useAppStore';
import { PodMark } from '@/components/redesign';

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
                <PodMark label={name.charAt(0)} kind="mute" size={18} />
                <span className="truncate">{name}</span>
              </Link>
            ))}
          </div>
        </>
      )}

      <div className="mt-auto pt-3.5 border-t border-border flex items-center gap-2.5 px-1.5">
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
