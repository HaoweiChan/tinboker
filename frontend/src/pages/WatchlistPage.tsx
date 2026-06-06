import { useEffect, useMemo, useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { Segmented, EpisodeCardV2, ListRow } from '@/components/redesign';
import { apiEpisodeToCardV2 } from '@/components/redesign/episodeAdapter';
import { getPodcastEpisodes, getSortedPodcasts, type Episode as ApiEpisode, type Podcast } from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';
import { useSubscriptions, useWatchlist } from '@/store/useAppStore';
import { useStockPriceMap } from '@/hooks/useStockPriceMap';
import { useTranslationMap } from '@/hooks/useTranslationMap';
import { useEpisodeSentimentMap } from '@/hooks/useEpisodeSentimentMap';
import { useStockSummaries } from '@/hooks/useStockSummaries';
import { getStockLabel } from '@/utils/stockDisplay';
import { Link } from 'react-router-dom';
import { TickerAvatar } from '@/components/common/TickerAvatar';

type Tab = 'podcasters' | 'tickers';

export const WatchlistPage: React.FC = () => {
  const subscriptions = useSubscriptions();
  const watchlist = useWatchlist();
  const [tab, setTab] = useState<Tab>('podcasters');
  const [episodes, setEpisodes] = useState<ApiEpisode[]>([]);
  const [podcasts, setPodcasts] = useState<Podcast[]>([]);
  const episodeTickers = useMemo(() => episodes.flatMap((ep) => ep.related_tickers ?? []), [episodes]);
  const priceMap = useStockPriceMap(episodeTickers);
  const rawTranslationMap = useTranslationMap(episodeTickers);
  // Flatten to ticker → displayName for the adapter (mirrors HomeFeed).
  const translationMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const [k, v] of rawTranslationMap) m.set(k, v.displayName);
    return m;
  }, [rawTranslationMap]);
  // Podcast cover art (name → image_url) so watchlist cards match the homepage.
  const podcastImageMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const p of podcasts) {
      if (p.name && p.image_url) map.set(p.name, p.image_url);
    }
    return map;
  }, [podcasts]);
  // Per-(episode, ticker) sentiment for the visible cards (async; chips populate after render).
  const visibleEpisodeIds = useMemo(() => episodes.map((e) => e.id), [episodes]);
  const sentimentMap = useEpisodeSentimentMap(visibleEpisodeIds);
  const [loadingEps, setLoadingEps] = useState(false);

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
    return () => {
      alive = false;
    };
  }, [tab, subscriptions]);

  const sortedWatchlist = useMemo(() => [...watchlist], [watchlist]);
  const summaries = useStockSummaries(sortedWatchlist);

  return (
    <>
      <SEO title="自選" description="追蹤的節目與個股。" />
      <PageContent>
        <h1 className="text-[22px] font-semibold tracking-[-0.02em] mb-3.5">自選</h1>
        <div className="mb-[18px]">
          <Segmented options={[{ value: 'podcasters', label: `追蹤節目 ${subscriptions.length}` }, { value: 'tickers', label: `追蹤個股 ${watchlist.length}` }] as const} value={tab} onChange={setTab} />
        </div>

        {tab === 'podcasters' ? (
          subscriptions.length === 0 ? (
            <div className="bg-card border border-border rounded-md p-10 text-center text-[13px] text-muted-foreground">
              尚未追蹤任何節目 — 去 <Link to="/podcaster" className="text-accent-info hover:underline">節目</Link> 頁追蹤幾個吧。
            </div>
          ) : loadingEps ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="bg-card border border-border rounded-md h-[180px] animate-pulse" />
              ))}
            </div>
          ) : episodes.length === 0 ? (
            <div className="bg-card border border-border rounded-md p-10 text-center text-[13px] text-muted-foreground">追蹤的節目目前沒有最新集數。</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {episodes.map((ep) => (
                <EpisodeCardV2 key={ep.id} {...apiEpisodeToCardV2(ep, priceMap, podcastImageMap, translationMap, sentimentMap.get(ep.id))} />
              ))}
            </div>
          )
        ) : watchlist.length === 0 ? (
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
        )}
      </PageContent>
    </>
  );
};
