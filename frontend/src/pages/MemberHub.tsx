import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Lock, Search, Star } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { Modal } from '@/components/ui/Modal';
import { EpisodeCardV2 } from '@/components/redesign';
import { apiEpisodeToCardV2 } from '@/components/redesign/episodeAdapter';
import { SubscribedPodcasters } from '@/components/profile/SubscribedPodcasters';
import { SubscribedTickers } from '@/components/profile/SubscribedTickers';
import { SubscribedTopics } from '@/components/profile/SubscribedTopics';
import { PlanCard } from '@/components/membership/PlanCard';
import { PicksPage } from '@/pages/PicksPage';
import { useAppStore } from '@/store/useAppStore';
import { useBookmarkedEpisodes } from '@/hooks/useBookmarkedEpisodes';
import { useStockPriceMap } from '@/hooks/useStockPriceMap';
import { useStockPriceSinceMap } from '@/hooks/useStockPriceSinceMap';
import { getSortedStocks } from '@/services/api';
import { fetchWithFallback } from '@/services/api/migration';
import { authApi, type AuthResponse } from '@/services/api/auth';
import { userApi } from '@/services/api/user';
import { formatMemberUntil } from '@/lib/date';

type Tab = 'picks' | 'podcasters' | 'tickers' | 'topics' | 'episodes';
const VALID_TABS: readonly Tab[] = ['picks', 'podcasters', 'tickers', 'topics', 'episodes'];

interface StockRow {
  symbol: string;
  name: string;
}

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

/** /member — the single "my stuff" home for every signed-in user (route gating
 *  lives in App.tsx's MemberRoute, which sends logged-out visitors to
 *  MembershipPage instead). 走勢 is the first tab: members get PicksPage,
 *  everyone else gets the plan pitch — PicksPage must never mount for a
 *  non-member (see the `isMember` guard below), or its returns endpoint 402s. */
export const MemberHub: React.FC = () => {
  const navigate = useNavigate();
  const { watchlist, toggleWatchlist, token } = useAppStore();
  const [userInfo, setUserInfo] = useState<AuthResponse['user'] | null>(null);
  const [userLoading, setUserLoading] = useState(true);

  const [apiWatchlist, setApiWatchlist] = useState<string[]>([]);
  const [podcastSubs, setPodcastSubs] = useState<string[]>([]);
  const [episodeBookmarks, setEpisodeBookmarks] = useState<string[]>([]);
  const [tagSubs, setTagSubs] = useState<string[]>([]);

  const { episodes: bookmarked, resolved: bookmarksResolved } = useBookmarkedEpisodes(episodeBookmarks, {
    repair: true,
    onChange: setEpisodeBookmarks,
  });
  const episodeTickers = useMemo(() => bookmarked.flatMap((ep) => ep.related_tickers ?? []), [bookmarked]);
  const priceMap = useStockPriceMap(episodeTickers);
  const priceSinceMap = useStockPriceSinceMap(bookmarked);

  // Membership comes from the store (hydrated before MemberRoute mounts this page),
  // not from the page's own /me fetch: that resolves a beat later, which flashed a
  // member onto 訂閱節目 before flipping to 走勢 and briefly showed them the lock.
  const storeUser = useAppStore((st) => st.user);
  const isMember = Boolean(storeUser?.is_member);

  // Tab is URL-addressable (?tab=…) so the sidebar's "我的" links can deep-link.
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get('tab') as Tab | null;
  const defaultTab: Tab = isMember ? 'picks' : 'podcasters';
  const tab: Tab = tabParam && VALID_TABS.includes(tabParam) ? tabParam : defaultTab;
  const setTab = (t: Tab) =>
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set('tab', t);
        return next;
      },
      { replace: true },
    );
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<StockRow[]>([]);

  useEffect(() => {
    if (!token) {
      setUserInfo(null);
      setUserLoading(false);
      return;
    }
    setUserLoading(true);
    authApi
      .getCurrentUser(token)
      .then(setUserInfo)
      .catch((e) => {
        console.error('Failed to fetch user info:', e);
        setUserInfo(null);
      })
      .finally(() => setUserLoading(false));
  }, [token]);

  useEffect(() => {
    if (!token) {
      setApiWatchlist([]);
      setPodcastSubs([]);
      setEpisodeBookmarks([]);
      setTagSubs([]);
      return;
    }
    if (userInfo) {
      setApiWatchlist(userInfo.watchlist || []);
      setPodcastSubs(userInfo.podcast_subscriptions || []);
      setEpisodeBookmarks(userInfo.episode_bookmarks || []);
      setTagSubs(userInfo.tag_subscriptions || []);
      return;
    }
    Promise.all([
      userApi.getWatchlist().catch(() => [] as string[]),
      userApi.getPodcastSubscriptions().catch(() => [] as string[]),
      userApi.getEpisodeBookmarks().catch(() => [] as string[]),
      userApi.getTagSubscriptions().catch(() => [] as string[]),
    ]).then(([w, p, e, t]) => {
      setApiWatchlist(w);
      setPodcastSubs(p);
      setEpisodeBookmarks(e);
      setTagSubs(t);
    });
  }, [token, userInfo]);

  const effectiveWatchlist = useMemo(() => (userInfo?.watchlist !== undefined ? userInfo.watchlist || [] : token ? apiWatchlist : watchlist), [userInfo, token, apiWatchlist, watchlist]);

  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults([]);
      return;
    }
    let alive = true;
    fetchWithFallback<unknown[]>(() => getSortedStocks({ q: searchQuery, limit: 40 }), [], `getSortedStocks:search`)
      .catch(() => [] as unknown[])
      .then((res) => {
        if (!alive) return;
        setSearchResults(
          (Array.isArray(res) ? res : []).map((s) => {
            const o = s as { ticker?: string; symbol?: string; name?: string };
            return { symbol: o.ticker || o.symbol || '', name: o.name || '' };
          }).filter((r) => r.symbol),
        );
      });
    return () => {
      alive = false;
    };
  }, [searchQuery]);

  const TABS: { id: Tab; label: string; locked?: boolean }[] = [
    { id: 'picks', label: '走勢', locked: !isMember },
    { id: 'podcasters', label: `訂閱節目 ${podcastSubs.length}` },
    { id: 'tickers', label: `自選股票 ${effectiveWatchlist.length}` },
    { id: 'topics', label: `追蹤話題 ${tagSubs.length}` },
    { id: 'episodes', label: `收藏集數 ${bookmarked.length || episodeBookmarks.length}` },
  ];

  const memberUntilLabel = storeUser?.member_until ? formatMemberUntil(storeUser.member_until) : null;

  return (
    <>
      <SEO title="會員專區" description="訂閱、收藏、留言與走勢功能。" />
      <PageContent>
        {/* Identity card */}
        <div className="bg-card border border-border rounded-md p-6 mb-5">
          {userLoading ? (
            <div className="flex items-center gap-4">
              <div className="w-[72px] h-[72px] rounded-full bg-muted animate-pulse" />
              <div className="flex-1">
                <div className="h-5 w-40 bg-muted rounded animate-pulse mb-2" />
                <div className="h-3 w-56 bg-muted rounded animate-pulse" />
              </div>
            </div>
          ) : userInfo ? (
            <div className="flex items-start gap-4">
              {userInfo.avatar ? (
                <img src={userInfo.avatar} alt={userInfo.name} className="w-[72px] h-[72px] rounded-full object-cover shrink-0" />
              ) : (
                <div className="w-[72px] h-[72px] rounded-full grid place-items-center text-white text-2xl font-semibold bg-accent-info shrink-0">{initials(userInfo.name)}</div>
              )}
              <div className="min-w-0">
                <h1 className="text-2xl font-semibold tracking-[-0.01em]">{userInfo.name}</h1>
                <div className="text-sm text-muted-foreground mt-0.5">{userInfo.email}</div>
                <div className="mt-1.5 text-sm">
                  {isMember ? (
                    <span className="flex items-center gap-2 flex-wrap">
                      <span className="text-accent-info font-medium">會員 · 有效至 {memberUntilLabel}</span>
                      <Link to="/membership" className="text-accent-info hover:underline text-xs">管理訂閱</Link>
                    </span>
                  ) : (
                    <span className="flex items-center gap-2 flex-wrap">
                      <span className="text-muted-foreground">免費會員</span>
                      <Link to="/member?tab=picks" className="text-accent-info hover:underline text-xs">升級</Link>
                    </span>
                  )}
                </div>
                <div className="flex gap-4 mt-2.5 text-xs text-muted-foreground">
                  <span><strong className="text-foreground font-mono mr-1 tabular-nums">{podcastSubs.length}</strong>追蹤節目</span>
                  <span><strong className="text-foreground font-mono mr-1 tabular-nums">{effectiveWatchlist.length}</strong>自選股</span>
                  <span><strong className="text-foreground font-mono mr-1 tabular-nums">{bookmarked.length || episodeBookmarks.length}</strong>收藏集數</span>
                  {formatJoin(userInfo.created_at) && <span>· {formatJoin(userInfo.created_at)}</span>}
                </div>
              </div>
            </div>
          ) : token ? (
            <div className="flex items-center gap-4">
              <div className="w-[72px] h-[72px] rounded-full grid place-items-center text-white text-2xl font-semibold bg-accent-info shrink-0">?</div>
              <div className="min-w-0">
                <div className="text-sm text-muted-foreground">已登入</div>
                <div className="flex gap-4 mt-2.5 text-xs text-muted-foreground">
                  <span><strong className="text-foreground font-mono mr-1 tabular-nums">{podcastSubs.length}</strong>追蹤節目</span>
                  <span><strong className="text-foreground font-mono mr-1 tabular-nums">{effectiveWatchlist.length}</strong>自選股</span>
                  <span><strong className="text-foreground font-mono mr-1 tabular-nums">{bookmarked.length || episodeBookmarks.length}</strong>收藏集數</span>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center py-6 text-sm text-muted-foreground">
              請先登入以查看會員專區 — <button onClick={() => navigate('/')} className="text-accent-info hover:underline">前往首頁登入</button>
            </div>
          )}
        </div>

        {/* Tabs */}
        <div className="flex gap-1.5 mb-4 overflow-x-auto pb-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              data-active={tab === t.id ? 'true' : undefined}
              className="filter-pill inline-flex items-center gap-1.5"
            >
              {t.locked && <Lock size={12} aria-label="會員功能" />}
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {tab === 'picks' && (
          isMember ? <PicksPage embedded /> : <PlanCard />
        )}

        {tab === 'podcasters' && (
          podcastSubs.length === 0 ? (
            <div className="bg-card border border-border rounded-md p-10 text-center text-sm text-muted-foreground">尚未追蹤任何節目。</div>
          ) : (
            <SubscribedPodcasters names={podcastSubs} />
          )
        )}

        {tab === 'tickers' && (
          <>
            {effectiveWatchlist.length === 0 ? (
              <div className="bg-card border border-border rounded-md p-10 text-center text-sm text-muted-foreground">尚未加入任何自選標的。</div>
            ) : (
              <SubscribedTickers tickers={effectiveWatchlist} />
            )}
            <button type="button" onClick={() => setSearchOpen(true)} className="mt-3 w-full border border-dashed border-border rounded-md py-6 text-sm text-muted-foreground hover:border-foreground/30 hover:text-foreground transition-colors">+ 新增自選</button>
          </>
        )}

        {tab === 'topics' && (
          tagSubs.length === 0 ? (
            <div className="bg-card border border-border rounded-md p-10 text-center text-sm text-muted-foreground">尚未追蹤任何話題。</div>
          ) : (
            <SubscribedTopics tagSubs={tagSubs} />
          )
        )}

        {tab === 'episodes' && (
          bookmarked.length === 0 ? (
            <div className="bg-card border border-border rounded-md p-10 text-center text-sm text-muted-foreground">
              {episodeBookmarks.length === 0
                ? '目前沒有收藏的集數。'
                : bookmarksResolved
                  ? '收藏的集數目前無法載入，可能已下架。稍後再試一次吧。'
                  : '載入中…'}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {bookmarked.map((ep) => (
                <EpisodeCardV2 key={ep.id} {...apiEpisodeToCardV2(ep, priceMap, undefined, undefined, undefined, priceSinceMap)} />
              ))}
            </div>
          )
        )}
      </PageContent>

      <Modal isOpen={searchOpen} onClose={() => setSearchOpen(false)} title="新增自選標的">
        <div className="p-4 border-b border-border">
          <label className="flex items-center gap-2 bg-muted rounded-md px-3 py-2">
            <Search size={16} className="text-muted-foreground shrink-0" />
            <input autoFocus value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} placeholder="搜尋代號或名稱…" className="flex-1 bg-transparent outline-none text-sm" />
          </label>
        </div>
        <div className="max-h-[60vh] overflow-y-auto">
          {searchResults.length === 0 ? (
            <div className="p-8 text-center text-sm text-muted-foreground">{searchQuery ? '沒有找到符合的標的' : '輸入代號或名稱開始搜尋'}</div>
          ) : (
            searchResults.map((r) => {
              const selected = (token ? apiWatchlist : watchlist).includes(r.symbol);
              return (
                <button
                  key={r.symbol}
                  type="button"
                  onClick={async () => {
                    await toggleWatchlist(r.symbol);
                    if (token) {
                      try {
                        setApiWatchlist(await userApi.getWatchlist());
                      } catch {
                        /* ignore */
                      }
                    }
                  }}
                  className="flex items-center justify-between w-full p-4 hover:bg-muted transition-colors text-left border-b border-border last:border-b-0"
                >
                  <span className="min-w-0">
                    <span className="block font-mono text-sm font-semibold">{r.symbol}</span>
                    <span className="block text-xs text-muted-foreground truncate">{r.name}</span>
                  </span>
                  <Star size={18} className={selected ? 'text-accent-info' : 'text-muted-foreground'} fill={selected ? 'currentColor' : 'none'} />
                </button>
              );
            })
          )}
        </div>
      </Modal>
    </>
  );
};

export default MemberHub;
