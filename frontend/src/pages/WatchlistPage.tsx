import { useEffect, useMemo, useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { Segmented, EpisodeCardV2, ListRow } from '@/components/redesign';
import { apiEpisodeToCardV2 } from '@/components/redesign/episodeAdapter';
import { getPodcastEpisodes, type Episode as ApiEpisode } from '@/services/api/podcasts';
import { useSubscriptions, useWatchlist } from '@/store/useAppStore';
import { useStockPriceMap } from '@/hooks/useStockPriceMap';
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
  const episodeTickers = useMemo(() => episodes.flatMap((ep) => ep.related_tickers ?? []), [episodes]);
  const priceMap = useStockPriceMap(episodeTickers);
  const [loadingEps, setLoadingEps] = useState(false);

  useEffect(() => {
    if (tab !== 'podcasters' || subscriptions.length === 0) return;
    let alive = true;
    setLoadingEps(true);
    (async () => {
      const arrays = await Promise.all(
        subscriptions.slice(0, 12).map((name) =>
          getPodcastEpisodes(name, { sortBy: 'spotify_release_date', order: 'desc', limit: 3, includeContent: false }).catch(() => [] as ApiEpisode[]),
        ),
      );
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
                <EpisodeCardV2 key={ep.id} {...apiEpisodeToCardV2(ep, priceMap)} />
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
