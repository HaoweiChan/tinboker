import { useEffect, useState } from 'react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { ChevronRight, Settings, Star } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { PlanCard } from '@/components/membership/PlanCard';
import { PicksPage } from '@/pages/PicksPage';
import { useAppStore } from '@/store/useAppStore';
import { authApi, type AuthResponse } from '@/services/api/auth';
import { userApi } from '@/services/api/user';
import { formatMemberUntil } from '@/lib/date';

/** The saved lists moved to /watchlist — keep old ?tab= deep links working. */
const MOVED_TABS: readonly string[] = ['podcasters', 'tickers', 'topics', 'episodes'];

function formatJoin(createdAt?: string): string {
  if (!createdAt) return '';
  const d = new Date(createdAt);
  return Number.isNaN(d.getTime()) ? '' : `${d.getFullYear()} 年 ${d.getMonth() + 1} 月加入`;
}
function initials(name?: string): string {
  return (name || '?')
    .split(/\s+/)
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();
}

/** /member — what membership buys: 走勢 and 週報, plus the subscription's own state.
 *  Saved items are NOT here; they're a personal utility reached from the header
 *  menu (/watchlist), so this page stays about the paid product. Route gating
 *  lives in App.tsx's MemberRoute, which sends logged-out visitors to
 *  MembershipPage. PicksPage must never mount for a non-member (the `isMember`
 *  guard below), or its returns endpoint 402s. */
export const MemberHub: React.FC = () => {
  const navigate = useNavigate();
  const token = useAppStore((st) => st.token);
  const localWatchlist = useAppStore((st) => st.watchlist);
  const [userInfo, setUserInfo] = useState<AuthResponse['user'] | null>(null);
  const [userLoading, setUserLoading] = useState(true);
  // Only what PicksPage's 我的 filter needs — the lists themselves live on /watchlist.
  const [apiWatchlist, setApiWatchlist] = useState<string[]>([]);
  const [podcastSubs, setPodcastSubs] = useState<string[]>([]);

  // Membership comes from the store (hydrated before MemberRoute mounts this page),
  // not from the page's own /me fetch: that resolves a beat later, which flashed the
  // plan pitch at a paying member.
  const storeUser = useAppStore((st) => st.user);
  const isMember = Boolean(storeUser?.is_member);
  const [searchParams] = useSearchParams();
  const movedTab = searchParams.get('tab');

  useEffect(() => {
    if (!token) {
      setUserInfo(null);
      setUserLoading(false);
      return;
    }
    setUserLoading(true);
    authApi
      .getCurrentUser(token)
      .then((u) => {
        setUserInfo(u);
        setApiWatchlist(u.watchlist || []);
        setPodcastSubs(u.podcast_subscriptions || []);
      })
      .catch((e) => {
        console.error('Failed to fetch user info:', e);
        setUserInfo(null);
      })
      .finally(() => setUserLoading(false));
  }, [token]);

  useEffect(() => {
    if (!token || userInfo) return;
    Promise.all([
      userApi.getWatchlist().catch(() => [] as string[]),
      userApi.getPodcastSubscriptions().catch(() => [] as string[]),
    ]).then(([w, p]) => {
      setApiWatchlist(w);
      setPodcastSubs(p);
    });
  }, [token, userInfo]);

  // After the hooks: an old deep link to a saved list is now a redirect.
  if (movedTab && MOVED_TABS.includes(movedTab)) {
    return <Navigate to={`/watchlist?tab=${movedTab}`} replace />;
  }

  const effectiveWatchlist = token ? apiWatchlist : localWatchlist;
  const memberUntilLabel = storeUser?.member_until ? formatMemberUntil(storeUser.member_until) : null;

  return (
    <>
      <SEO title="會員專區" description="會員的走勢追蹤與每週週報。" />
      <PageContent>
        {/* Identity + subscription state */}
        <div className="bg-card border border-border rounded-md p-4 sm:p-6 mb-4">
          {userLoading ? (
            <div className="flex items-center gap-4">
              <div className="w-[72px] h-[72px] rounded-full bg-muted animate-pulse" />
              <div className="flex-1">
                <div className="h-5 w-40 bg-muted rounded animate-pulse mb-2" />
                <div className="h-3 w-56 bg-muted rounded animate-pulse" />
              </div>
            </div>
          ) : userInfo ? (
            <div className="flex items-start gap-3 sm:gap-4">
              {userInfo.avatar ? (
                <img src={userInfo.avatar} alt={userInfo.name} className="w-14 h-14 sm:w-[72px] sm:h-[72px] rounded-full object-cover shrink-0" />
              ) : (
                <div className="w-14 h-14 sm:w-[72px] sm:h-[72px] rounded-full grid place-items-center text-white text-xl sm:text-2xl font-semibold bg-accent-info shrink-0">{initials(userInfo.name)}</div>
              )}
              <div className="min-w-0">
                <h1 className="text-xl sm:text-2xl font-semibold tracking-[-0.01em] truncate">{userInfo.name}</h1>
                <div className="text-sm text-muted-foreground mt-0.5 truncate">{userInfo.email}</div>
                <div className="mt-1.5 text-sm">
                  {/* These were plain coloured text and didn't read as tappable — a
                      bordered pill is the smallest thing that does. */}
                  {isMember ? (
                    <span className="flex items-center gap-x-2.5 gap-y-1 flex-wrap">
                      <span className="text-accent-info font-medium whitespace-nowrap">會員 · 有效至 {memberUntilLabel}</span>
                      <Link
                        to="/membership"
                        className="inline-flex items-center rounded-md border border-border bg-card px-2.5 py-1 text-xs font-medium text-foreground hover:bg-muted hover:border-foreground/30 transition-colors"
                      >
                        管理訂閱
                      </Link>
                    </span>
                  ) : (
                    <span className="flex items-center gap-2.5 flex-wrap">
                      <span className="text-muted-foreground">免費會員</span>
                      <Link
                        to="/membership"
                        className="inline-flex items-center rounded-md bg-foreground px-2.5 py-1 text-xs font-semibold text-background hover:opacity-90 transition-opacity"
                      >
                        升級
                      </Link>
                    </span>
                  )}
                </div>
                {formatJoin(userInfo.created_at) && (
                  <div className="mt-2 text-xs text-muted-foreground">{formatJoin(userInfo.created_at)}</div>
                )}
              </div>
            </div>
          ) : token ? (
            <div className="text-sm text-muted-foreground">已登入</div>
          ) : (
            <div className="text-center py-6 text-sm text-muted-foreground">
              請先登入以查看會員專區 — <button onClick={() => navigate('/')} className="text-accent-info hover:underline">前往首頁登入</button>
            </div>
          )}
        </div>

        {/* The two personal utilities that used to be tabs here. */}
        <div className="grid grid-cols-2 gap-2.5 mb-5">
          <Link to="/watchlist" className="flex items-center gap-2 bg-card border border-border rounded-md px-3.5 py-3 text-sm hover:border-foreground/25 transition-colors">
            <Star size={16} className="text-muted-foreground shrink-0" />
            <span className="flex-1 truncate">收藏</span>
            <ChevronRight size={14} className="text-muted-foreground shrink-0" />
          </Link>
          <Link to="/settings" className="flex items-center gap-2 bg-card border border-border rounded-md px-3.5 py-3 text-sm hover:border-foreground/25 transition-colors">
            <Settings size={16} className="text-muted-foreground shrink-0" />
            <span className="flex-1 truncate">帳號設定</span>
            <ChevronRight size={14} className="text-muted-foreground shrink-0" />
          </Link>
        </div>

        {/* 週報 — the other half of what membership is for; the page itself is public. */}
        <Link to="/weekly" className="flex items-center gap-3 bg-card border border-border rounded-md p-4 mb-5 hover:border-foreground/25 transition-colors">
          <div className="min-w-0 flex-1">
            <div className="text-base font-semibold tracking-[-0.01em]">每週週報</div>
            <div className="text-xs text-muted-foreground mt-0.5">這一週各節目聊了哪些個股與題材、多空怎麼變。</div>
          </div>
          <ChevronRight size={16} className="text-muted-foreground shrink-0" />
        </Link>

        {/* 走勢 — members only; everyone else gets the plan pitch. */}
        <h2 className="text-base font-semibold tracking-[-0.01em] mb-2.5">走勢</h2>
        {isMember ? (
          <PicksPage embedded mySubscribedPodcasts={podcastSubs} myWatchlistTickers={effectiveWatchlist} />
        ) : (
          <PlanCard />
        )}
      </PageContent>
    </>
  );
};

export default MemberHub;
