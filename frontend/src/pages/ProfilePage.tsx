import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Search, Star, ChevronRight } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { Modal } from '@/components/ui/Modal';
import { EpisodeCardV2, ListRow, PodMark } from '@/components/redesign';
import { apiEpisodeToCardV2 } from '@/components/redesign/episodeAdapter';
import { cn } from '@/lib/utils';
import { useAppStore } from '@/store/useAppStore';
import { useStockPriceMap } from '@/hooks/useStockPriceMap';
import { useStockPriceSinceMap } from '@/hooks/useStockPriceSinceMap';
import {
  getSortedStocks,
  getPodcastByName,
  getEpisodeById,
  type Episode as ApiEpisode,
  type Podcast,
} from '@/services/api';
import { fetchWithFallback } from '@/services/api/migration';
import { authApi, type AuthResponse } from '@/services/api/auth';
import { userApi } from '@/services/api/user';

type Tab = 'podcasters' | 'tickers' | 'topics' | 'episodes';
const VALID_TABS: readonly Tab[] = ['podcasters', 'tickers', 'topics', 'episodes'];

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

export const ProfilePage: React.FC = () => {
  const navigate = useNavigate();
  const { watchlist, toggleWatchlist, token } = useAppStore();
  const [userInfo, setUserInfo] = useState<AuthResponse['user'] | null>(null);
  const [userLoading, setUserLoading] = useState(true);

  const [apiWatchlist, setApiWatchlist] = useState<string[]>([]);
  const [podcastSubs, setPodcastSubs] = useState<string[]>([]);
  const [episodeBookmarks, setEpisodeBookmarks] = useState<string[]>([]);
  const [tagSubs, setTagSubs] = useState<string[]>([]);

  const [stockRows, setStockRows] = useState<StockRow[]>([]);
  const [podcasters, setPodcasters] = useState<Podcast[]>([]);
  const [bookmarked, setBookmarked] = useState<ApiEpisode[]>([]);
  const episodeTickers = useMemo(() => bookmarked.flatMap((ep) => ep.related_tickers ?? []), [bookmarked]);
  const priceMap = useStockPriceMap(episodeTickers);
  const priceSinceMap = useStockPriceSinceMap(bookmarked);

  // Tab is URL-addressable (?tab=…) so the sidebar's "我的" links can deep-link.
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get('tab') as Tab | null;
  const tab: Tab = tabParam && VALID_TABS.includes(tabParam) ? tabParam : 'podcasters';
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

  // Hydrate watchlist tickers → names (best effort).
  useEffect(() => {
    if (effectiveWatchlist.length === 0) {
      setStockRows([]);
      return;
    }
    let alive = true;
    fetchWithFallback<unknown[]>(() => getSortedStocks({ limit: 500 }), [], 'getSortedStocks:profile')
      .catch(() => [] as unknown[])
      .then((all) => {
        if (!alive) return;
        const nameOf = new Map<string, string>();
        for (const s of Array.isArray(all) ? all : []) {
          const o = s as { ticker?: string; symbol?: string; name?: string };
          const t = o.ticker || o.symbol;
          if (t) nameOf.set(t.toUpperCase().split('.')[0], o.name || t);
        }
        setStockRows(effectiveWatchlist.map((sym) => ({ symbol: sym, name: nameOf.get(sym.toUpperCase().split('.')[0]) || sym })));
      });
    return () => {
      alive = false;
    };
  }, [effectiveWatchlist]);

  useEffect(() => {
    if (podcastSubs.length === 0) {
      setPodcasters([]);
      return;
    }
    let alive = true;
    Promise.all(podcastSubs.map((n) => fetchWithFallback<Podcast | null>(() => getPodcastByName(n), null, `getPodcastByName:${n}`).catch(() => null))).then((arr) => {
      if (alive) setPodcasters(arr.filter((p): p is Podcast => p != null));
    });
    return () => {
      alive = false;
    };
  }, [podcastSubs]);

  useEffect(() => {
    if (episodeBookmarks.length === 0) {
      setBookmarked([]);
      return;
    }
    let alive = true;
    Promise.all(
      episodeBookmarks.map((bookmarkId) => {
        const [podcastName, ...rest] = bookmarkId.split('_');
        return fetchWithFallback<ApiEpisode | null>(() => getEpisodeById(podcastName, rest.join('_')), null, `getEpisodeById:${bookmarkId}`).catch(() => null);
      }),
    ).then((arr) => {
      if (alive) setBookmarked(arr.filter((e): e is ApiEpisode => e != null));
    });
    return () => {
      alive = false;
    };
  }, [episodeBookmarks]);

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

  const TABS: { id: Tab; label: string }[] = [
    { id: 'podcasters', label: `訂閱節目 ${podcasters.length || podcastSubs.length}` },
    { id: 'tickers', label: `自選股票 ${stockRows.length || effectiveWatchlist.length}` },
    { id: 'topics', label: `追蹤話題 ${tagSubs.length}` },
    { id: 'episodes', label: `收藏集數 ${bookmarked.length || episodeBookmarks.length}` },
  ];

  return (
    <>
      <SEO title="個人檔案" description="訂閱、收藏與留言。" />
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
                <h1 className="text-[20px] font-semibold tracking-[-0.01em]">{userInfo.name}</h1>
                <div className="text-[13px] text-muted-foreground mt-0.5">{userInfo.email}</div>
                <div className="flex gap-4 mt-2.5 text-[12px] text-muted-foreground">
                  <span><strong className="text-foreground font-mono mr-1 tabular-nums">{podcasters.length || podcastSubs.length}</strong>追蹤節目</span>
                  <span><strong className="text-foreground font-mono mr-1 tabular-nums">{stockRows.length || effectiveWatchlist.length}</strong>自選股</span>
                  <span><strong className="text-foreground font-mono mr-1 tabular-nums">{bookmarked.length || episodeBookmarks.length}</strong>收藏集數</span>
                  {formatJoin(userInfo.created_at) && <span>· {formatJoin(userInfo.created_at)}</span>}
                </div>
              </div>
            </div>
          ) : token ? (
            <div className="flex items-center gap-4">
              <div className="w-[72px] h-[72px] rounded-full grid place-items-center text-white text-2xl font-semibold bg-accent-info shrink-0">?</div>
              <div className="min-w-0">
                <div className="text-[13px] text-muted-foreground">已登入</div>
                <div className="flex gap-4 mt-2.5 text-[12px] text-muted-foreground">
                  <span><strong className="text-foreground font-mono mr-1 tabular-nums">{podcasters.length || podcastSubs.length}</strong>追蹤節目</span>
                  <span><strong className="text-foreground font-mono mr-1 tabular-nums">{stockRows.length || effectiveWatchlist.length}</strong>自選股</span>
                  <span><strong className="text-foreground font-mono mr-1 tabular-nums">{bookmarked.length || episodeBookmarks.length}</strong>收藏集數</span>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center py-6 text-[13px] text-muted-foreground">
              請先登入以查看個人資料 — <button onClick={() => navigate('/')} className="text-accent-info hover:underline">前往首頁登入</button>
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
              className={cn(
                'px-3.5 py-1.5 rounded-full text-[12.5px] font-medium whitespace-nowrap transition-colors',
                tab === t.id ? 'bg-foreground text-background' : 'bg-muted text-foreground hover:bg-muted/70',
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {tab === 'podcasters' && (
          podcasters.length === 0 ? (
            <div className="bg-card border border-border rounded-md p-10 text-center text-[13px] text-muted-foreground">尚未追蹤任何節目。</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {podcasters.map((p) => (
                <button key={p.id || p.name} type="button" onClick={() => navigate(`/podcaster/${encodeURIComponent(p.name)}`)} className="flex items-center gap-3 bg-card border border-border rounded-md p-4 text-left transition-colors hover:border-foreground/25">
                  {p.image_url ? <img src={p.image_url} alt="" className="w-10 h-10 rounded-[9px] object-cover shrink-0" /> : <PodMark label={(p.name || '?').charAt(0)} kind="mute" size={40} />}
                  <div className="min-w-0">
                    <div className="text-[14px] font-semibold truncate">{p.name}</div>
                    <div className="text-[11px] text-muted-foreground font-mono tabular-nums">{p.episode_count ?? '—'} 集</div>
                  </div>
                </button>
              ))}
            </div>
          )
        )}

        {tab === 'tickers' && (
          <>
            {stockRows.length === 0 ? (
              <div className="bg-card border border-border rounded-md p-10 text-center text-[13px] text-muted-foreground">尚未加入任何自選標的。</div>
            ) : (
              <div className="space-y-1.5">
                {stockRows.map((r) => (
                  <ListRow
                    key={r.symbol}
                    title={
                      <span>
                        <span className="font-mono">{r.symbol}</span>
                        {r.name && r.name !== r.symbol && <span className="ml-2 font-normal text-muted-foreground">{r.name}</span>}
                      </span>
                    }
                    href={`/stock/${encodeURIComponent(r.symbol)}`}
                    trailing={<ChevronRight size={14} />}
                  />
                ))}
              </div>
            )}
            <button type="button" onClick={() => setSearchOpen(true)} className="mt-3 w-full border border-dashed border-border rounded-md py-6 text-[13px] text-muted-foreground hover:border-foreground/30 hover:text-foreground transition-colors">+ 新增自選</button>
          </>
        )}

        {tab === 'topics' && (
          tagSubs.length === 0 ? (
            <div className="bg-card border border-border rounded-md p-10 text-center text-[13px] text-muted-foreground">尚未追蹤任何話題。</div>
          ) : (
            <div className="flex flex-wrap gap-2">
              {tagSubs.map((t) => {
                const name = t.replace(/^#/, '');
                return (
                  <button key={t} type="button" onClick={() => navigate(`/topics/${encodeURIComponent(name)}`)} className="px-3.5 py-1.5 rounded-full bg-muted text-foreground text-[13px] font-medium hover:bg-accent-info-soft hover:text-accent-info transition-colors">
                    #{name}
                  </button>
                );
              })}
            </div>
          )
        )}

        {tab === 'episodes' && (
          bookmarked.length === 0 ? (
            <div className="bg-card border border-border rounded-md p-10 text-center text-[13px] text-muted-foreground">目前沒有收藏的集數。</div>
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
            <input autoFocus value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} placeholder="搜尋代號或名稱…" className="flex-1 bg-transparent outline-none text-[13px]" />
          </label>
        </div>
        <div className="max-h-[60vh] overflow-y-auto">
          {searchResults.length === 0 ? (
            <div className="p-8 text-center text-[13px] text-muted-foreground">{searchQuery ? '沒有找到符合的標的' : '輸入代號或名稱開始搜尋'}</div>
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
                    <span className="block font-mono text-[13px] font-semibold">{r.symbol}</span>
                    <span className="block text-[12px] text-muted-foreground truncate">{r.name}</span>
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

export default ProfilePage;
