import { useEffect, useMemo, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { SEO } from '@/components/common/SEO';
import { PageContent } from '@/components/layout/PageContent';
import { EpisodeCardV2 } from '@/components/redesign';
import { apiEpisodeToCardV2 } from '@/components/redesign/episodeAdapter';
import { getEpisodesBySector, getSortedPodcasts, type EpisodesBySectorResponse, type Episode as ApiEpisode, type Podcast, type SectorResolvedTicker } from '@/services/api/podcasts';
import { fetchWithFallback } from '@/services/api/migration';
import { useStockPriceMap } from '@/hooks/useStockPriceMap';
import { useStockPriceSinceMap } from '@/hooks/useStockPriceSinceMap';
import { useTranslationMap } from '@/hooks/useTranslationMap';

function resolvedTickerName(t: SectorResolvedTicker, translationMap: Map<string, string>): string {
  const upper = t.ticker.toUpperCase();
  const bare = upper.replace(/\.[A-Z]+$/i, '');
  for (const key of [upper, bare, `${bare}.TW`, `${bare}.KS`]) {
    const n = translationMap.get(key);
    if (n) return n;
  }
  return t.name || t.ticker;
}

export const SectorPage: React.FC = () => {
  const { exposureId } = useParams<{ exposureId: string }>();
  const [data, setData] = useState<EpisodesBySectorResponse | null>(null);
  const [podcasts, setPodcasts] = useState<Podcast[]>([]);
  const [loading, setLoading] = useState(true);

  const episodes = useMemo<ApiEpisode[]>(() => data?.episodes ?? [], [data]);
  const episodeTickers = useMemo(() => episodes.flatMap((ep) => ep.related_tickers ?? []), [episodes]);
  const resolvedTickers = useMemo<SectorResolvedTicker[]>(() => data?.resolved_tickers ?? [], [data]);
  const allTickers = useMemo(
    () => [...new Set([...episodeTickers, ...resolvedTickers.map((t) => t.ticker)])],
    [episodeTickers, resolvedTickers],
  );

  const priceMap = useStockPriceMap(episodeTickers);
  const priceSinceMap = useStockPriceSinceMap(episodes);
  const rawTranslationMap = useTranslationMap(allTickers);
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

  useEffect(() => {
    if (!exposureId) return;
    let alive = true;
    setLoading(true);
    (async () => {
      const [res, podcastList] = await Promise.all([
        fetchWithFallback<EpisodesBySectorResponse>(
          () => getEpisodesBySector(exposureId, 50, 0),
          { exposure_id: exposureId, display_name: '', exposure_type: 'sector', resolved_tickers: [], episodes: [], total: 0 },
          `getEpisodesBySector:${exposureId}`,
        ).catch(() => null),
        fetchWithFallback<Podcast[]>(
          () => getSortedPodcasts({ sortBy: 'updated_at', order: 'desc', limit: 200 }),
          [],
          'getSortedPodcasts',
        ).catch(() => [] as Podcast[]),
      ]);
      if (!alive) return;
      if (res) {
        const sorted = [...res.episodes].sort((a, b) => {
          const da = typeof a.spotify_release_date === 'string' ? Date.parse(a.spotify_release_date) : (a.spotify_release_date ?? a.created_time);
          const db = typeof b.spotify_release_date === 'string' ? Date.parse(b.spotify_release_date) : (b.spotify_release_date ?? b.created_time);
          return (db as number) - (da as number);
        });
        setData({ ...res, episodes: sorted });
      }
      setPodcasts(Array.isArray(podcastList) ? podcastList : []);
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, [exposureId]);

  const displayName = data?.display_name || '';
  // Never flash the raw exposure id (e.g. "sector_passive_components") while the
  // request is in flight or if it fails — show a skeleton, then the resolved name
  // (or a generic label as a last resort).
  const titleText = displayName || '產業 / 主題';
  const representativeTickers = resolvedTickers.slice(0, 8);

  return (
    <>
      <SEO
        title={titleText}
        description={`所有關於「${titleText}」產業 / 主題的 Podcast 摘要與市場討論。`}
      />
      <PageContent>
        <div className="flex items-start gap-5 bg-card border border-border rounded-md p-5 sm:p-6 mb-[18px]">
          <div className="flex-1 min-w-0">
            {loading ? (
              <div className="h-7 w-40 bg-muted rounded animate-pulse" />
            ) : (
              <h1 className="text-[22px] font-semibold tracking-[-0.02em]">{titleText}</h1>
            )}
            <p className="text-[13px] text-muted-foreground mt-1 max-w-[56ch] leading-[1.55]">
              {loading
                ? '載入中…'
                : `瀏覽所有關於「${titleText}」的 Podcast 摘要與市場討論 · ${episodes.length} 集。`}
            </p>
            {!loading && representativeTickers.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-3">
                {representativeTickers.map((t) => (
                  <Link
                    key={t.ticker}
                    to={`/stock/${encodeURIComponent(t.ticker)}`}
                    className="inline-flex items-center gap-1 text-[12px] px-2.5 py-0.5 rounded-full bg-muted hover:bg-muted/80 border border-border font-medium transition-colors"
                  >
                    <span className="font-mono text-[11px] text-muted-foreground">{t.ticker}</span>
                    <span>{resolvedTickerName(t, translationMap)}</span>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>

        <h2 className="text-[13px] font-semibold text-muted-foreground mb-3">相關集數</h2>
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="bg-card border border-border rounded-md h-[180px] animate-pulse" />
            ))}
          </div>
        ) : episodes.length === 0 ? (
          <div className="bg-card border border-border rounded-md p-10 text-center text-[13px] text-muted-foreground">目前沒有相關 Podcast 集數。</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {episodes.map((ep) => (
              <EpisodeCardV2 key={ep.id} {...apiEpisodeToCardV2(ep, priceMap, podcastImageMap, translationMap, undefined, priceSinceMap)} />
            ))}
          </div>
        )}
      </PageContent>
    </>
  );
};

export default SectorPage;
