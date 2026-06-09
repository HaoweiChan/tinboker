import { useEffect, useMemo, useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { Segmented, EpisodeCardV2, ListRow } from '@/components/redesign';
import { apiEpisodeToCardV2 } from '@/components/redesign/episodeAdapter';
import { getPodcastEpisodes, getSortedPodcasts, getEpisodeById, type Episode as ApiEpisode, type Podcast } from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';
import { userApi } from '@/services/api/user';
import { useAppStore, useSubscriptions, useWatchlist, useTagSubscriptions } from '@/store/useAppStore';
import { useStockPriceMap } from '@/hooks/useStockPriceMap';
import { useStockPriceSinceMap } from '@/hooks/useStockPriceSinceMap';
import { useTranslationMap } from '@/hooks/useTranslationMap';
import { useEpisodeSentimentMap } from '@/hooks/useEpisodeSentimentMap';
import { useStockSummaries } from '@/hooks/useStockSummaries';
import { getStockLabel } from '@/utils/stockDisplay';
import { Link } from 'react-router-dom';
import { TickerAvatar } from '@/components/common/TickerAvatar';

type Tab = 'podcasters' | 'tickers' | 'topics' | 'episodes';

export const WatchlistPage: React.FC = () => {
  const navigate = useNavigate();
  const token = useAppStore((s) => s.token);
  const localSubscriptions = useSubscriptions();
  const localWatchlist = useWatchlist();
  const localTagSubscriptions = useTagSubscriptions();
  const [tab, setTab] = useState<Tab>('podcasters');
  const [episodes, setEpisodes] = useState<ApiEpisode[]>([]);
  const [podcasts, setPodcasts] = useState<Podcast[]>([]);
  const [bookmarkedIds, setBookmarkedIds] = useState<string[]>([]);
  const [bookmarked, setBookmarked] = useState<ApiEpisode[]>([]);
  const [loadingEps, setLoadingEps] = useState(false);
  // Server-side data for logged-in users
  const [apiSubscriptions, setApiSubscriptions] = useState<string[]>([]);
  const [apiWatchlist, setApiWatchlist] = useState<string[]>([]);
  const [apiTagSubs, setApiTagSubs] = useState<string[]>([]);
  const [serverLoaded, setServerLoaded] = useState(false);

  // Effective lists: prefer server data for logged-in users, fall back to local store
  const subscriptions = useMemo(
    () => token && serverLoaded ? apiSubscriptions : localSubscriptions,
    [token, serverLoaded, apiSubscriptions, localSubscriptions],
  );
  const watchlist = useMemo(
    () => token && serverLoaded ? apiWatchlist : localWatchlist,
    [token, serverLoaded, apiWatchlist, localWatchlist],
  );
  const tagSubscriptions = useMemo(
    () => token && serverLoaded ? apiTagSubs : localTagSubscriptions,
    [token, serverLoaded, apiTagSubs, localTagSubscriptions],
  );

  // Fetch server-side user data on mount when logged in
  useEffect(() => {
    if (!token) {
      setServerLoaded(false);
      return;
    }
    Promise.all([
      userApi.getPodcastSubscriptions().catch(() => [] as string[]),
      userApi.getWatchlist().catch(() => [] as string[]),
      userApi.getTagSubscriptions().catch(() => [] as string[]),
      userApi.getEpisodeBookmarks().catch(() => [] as string[]),
    ]).then(([subs, wl, tags, bm]) => {
      setApiSubscriptions(subs);
      setApiWatchlist(wl);
      setApiTagSubs(tags);
      setBookmarkedIds(bm);
      setServerLoaded(true);
    });
  }, [token]);

  const episodeTickers = useMemo(() => episodes.flatMap((ep) => ep.related_tickers ?? []), [episodes]);
  const priceMap = useStockPriceMap(episodeTickers);
  const priceSinceMap = useStockPriceSinceMap(episodes);
  const rawTranslationMap = useTranslationMap(episodeTickers);
  const translationMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const [k, v] of rawTranslationMap) m.set(k, v.displayName);
    return m;
  }, [rawTranslationMap]);
  const podcastImageMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const p of podcasts) {
      if (p.name && p.image_url) map.set(p.name, p.image_url);
    }
    return map;
  }, [podcasts]);
  const visibleEpisodeIds = useMemo(() => episodes.map((e) => e.id), [episodes]);
  const sentimentMap = useEpisodeSentimentMap(visibleEpisodeIds);
  const bookmarkedTickers = useMemo(() => bookmarked.flatMap((ep) => ep.related_tickers ?? []), [bookmarked]);
  const bookmarkedPriceMap = useStockPriceMap(bookmarkedTickers);
  const bookmarkedPriceSinceMap = useStockPriceSinceMap(bookmarked);

  // Fetch subscribed podcast episodes
  useEffect(() => {
    if (tab !== 'podcasters' || subscriptions.length === 0) return;
    let alive = true;
    setLoadingEps(true);
    (async () => {
      const [arrays, podcastList] = await Promise.all([
        Promise.all(
          subscriptions.slice(0, 12).map((name) =>
            getPodcastEpisodes(name, { sortBy: 'spotify_release_date', order: 'desc', limit: 3, includeContent: false }).catch(() => [] as ApiEpisode[]),
          ),
        ),
        fetchWithFallback<Podcast[]>(
          () => getSortedPodcasts({ sortBy: 'updated_at', order: 'desc', limit: 200 }),
          [],
          'getSortedPodcasts:watchlist',
        ).catch(() => [] as Podcast[]),
      ]);
      if (!alive) return;
      const flat = arrays
        .flat()
        .sort((a, b) => {
          const da = typeof a.spotify_release_date === 'string' ? Date.parse(a.spotify_release_date) : (a.spotify_release_date ?? a.created_time);
          const db = typeof b.spotify_release_date === 'string' ? Date.parse(b.spotify_release_date) : (b.spotify_release_date ?? b.created_time);
          return (db as number) - (da as number);
        })
        .slice(0, 18);
      setEpisodes(flat);
      setPodcasts(Array.isArray(podcastList) ? podcastList : []);
      setLoadingEps(false);
    })();
    return () => { alive = false; };
  }, [tab, subscriptions]);

  // Fetch bookmarked episode IDs (for anonymous users only — logged-in fetched above)
  useEffect(() => {
    if (token) return;
    setBookmarkedIds([]);
  }, [token]);

  // Hydrate bookmarked episodes
  useEffect(() => {
    if (bookmarkedIds.length === 0) {
      setBookmarked([]);
      return;
    }
    let alive = true;
    Promise.all(
      bookmarkedIds.map((bookmarkId) => {
        const [podcastName, ...rest] = bookmarkId.split('_');
        return fetchWithFallback<ApiEpisode | null>(
          () => getEpisodeById(podcastName, rest.join('_')),
          null,
          `getEpisodeById:${bookmarkId}`,
        ).catch(() => null);
      }),
    ).then((arr) => {
      if (alive) setBookmarked(arr.filter((e): e is ApiEpisode => e != null));
    });
    return () => { alive = false; };
  }, [bookmarkedIds]);

  const sortedWatchlist = useMemo(() => [...watchlist], [watchlist]);
  const summaries = useStockSummaries(sortedWatchlist);

  // Show loading state while server data is being fetched for logged-in users
  const isLoading = token && !serverLoaded;

  return (
    <>
      <SEO title="自選" description="追蹤的節目與個股。" />
      <PageContent>
        <h1 className="text-[22px] font-semibold tracking-[-0.02em] mb-3.5">自選</h1>
        <div className="mb-[18px]">
          <Segmented
            options={[
              { value: 'podcasters', label: `訂閱節目 ${subscriptions.length}` },
              { value: 'tickers', label: `自選股票 ${watchlist.length}` },
              { value: 'topics', label: `追蹤話題 ${tagSubscriptions.length}` },
              { value: 'episodes', label: `收藏集數 ${bookmarked.length || bookmarkedIds.length}` },
            ] as const}
            value={tab}
            onChange={setTab}
          />
        </div>

        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="bg-card border border-border rounded-md h-[180px] animate-pulse" />
            ))}
          </div>
        ) : (
          <>
            {tab === 'podcasters' && (
              subscriptions.length === 0 ? (
                <div className="bg-card border border-border rounded-md p-10 text-center text-[13px] text-muted-foreground">
                  尚未訂閱任何節目 — 去 <Link to="/podcaster" className="text-accent-info hover:underline">節目</Link> 頁追蹤幾個吧。
                </div>
              ) : loadingEps ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="bg-card border border-border rounded-md h-[180px] animate-pulse" />
                  ))}
                </div>
              ) : episodes.length === 0 ? (
                <div className="bg-card border border-border rounded-md p-10 text-center text-[13px] text-muted-foreground">訂閱的節目目前沒有最新集數。</div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {episodes.map((ep) => (
                    <EpisodeCardV2 key={ep.id} {...apiEpisodeToCardV2(ep, priceMap, podcastImageMap, translationMap, sentimentMap.get(ep.id), priceSinceMap)} />
                  ))}
                </div>
              )
            )}

            {tab === 'tickers' && (
              watchlist.length === 0 ? (
                <div className="bg-card border border-border rounded-md p-10 text-center text-[13px] text-muted-foreground">
                  尚未加入任何自選股票 — 去 <Link to="/stock" className="text-accent-info hover:underline">個股</Link> 頁加入幾檔吧。
                </div>
              ) : (
                <div className="space-y-1.5">
                  {sortedWatchlist.map((sym) => {
                    const summary = summaries[sym];
                    const { primary, secondary } = getStockLabel({
                      ticker: sym,
                      name: summary?.name,
                      market: summary?.market,
                    });
                    return (
                      <ListRow
                        key={sym}
                        lead={<TickerAvatar ticker={sym} brandColor={summary?.brand_color} />}
                        title={<span>{primary}</span>}
                        subtitle={secondary ? <span className="font-mono">{secondary}</span> : undefined}
                        href={`/stock/${encodeURIComponent(sym)}`}
                        trailing={<ChevronRight size={14} />}
                      />
                    );
                  })}
                </div>
              )
            )}

            {tab === 'topics' && (
              tagSubscriptions.length === 0 ? (
                <div className="bg-card border border-border rounded-md p-10 text-center text-[13px] text-muted-foreground">
                  尚未追蹤任何話題 — 去 <Link to="/topics" className="text-accent-info hover:underline">話題</Link> 頁追蹤幾個吧。
                </div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {tagSubscriptions.map((t) => {
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
              bookmarked.length === 0 && bookmarkedIds.length === 0 ? (
                <div className="bg-card border border-border rounded-md p-10 text-center text-[13px] text-muted-foreground">目前沒有收藏的集數。</div>
              ) : bookmarked.length === 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {Array.from({ length: Math.min(bookmarkedIds.length, 4) }).map((_, i) => (
                    <div key={i} className="bg-card border border-border rounded-md h-[180px] animate-pulse" />
                  ))}
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {bookmarked.map((ep) => (
                    <EpisodeCardV2 key={ep.id} {...apiEpisodeToCardV2(ep, bookmarkedPriceMap, undefined, undefined, undefined, bookmarkedPriceSinceMap)} />
                  ))}
                </div>
              )
            )}
          </>
        )}
      </PageContent>
    </>
  );
};
